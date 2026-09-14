"""知乎黑客松 OAuth 与内容 API 的最小后端 wrapper。

本模块只实现本地 Skill 明确记录的 HTTP 契约：

* 黑客松 OAuth authorize/access_token；
* 代表 OAuth 用户调用 user/contents；
* 黑客松 story/knowledge 公共内容列表与详情。

App Key、Access Secret 和 OAuth access token 都只在后端边界出现。
本项目不把 CLI 当作 Python SDK，也不在这里重写 CLI 的 Access Secret
密钥链、重试或 MCP 能力。
"""

from __future__ import annotations

import json
import os
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


ZHIHU_OAUTH_AUTHORIZE_URL = "https://openapi.zhihu.com/authorize"
ZHIHU_OAUTH_TOKEN_URL = "https://openapi.zhihu.com/access_token"
ZHIHU_USER_PROFILE_URL = "https://openapi.zhihu.com/user"
ZHIHU_USER_CONTENTS_URL = "https://developer.zhihu.com/api/v1/user/contents"
ZHIHU_HACKATHON_API_BASE = "https://api.zhihu.com/km-indep-home/hackathon/v2"

SESSION_COOKIE_NAME = "zhihu_session"
OAUTH_STATE_COOKIE_NAME = "zhihu_oauth_state"
OAUTH_STATE_COOKIE_PATH = "/api/auth/zhihu"
DEFAULT_HTTP_TIMEOUT_SECONDS = 15.0
OAUTH_STATE_TTL_SECONDS = 600


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class ZhihuConfig:
    """运行时配置。

    `ZHIHU_OAUTH_APP_ID` 与 `ZHIHU_OAUTH_REDIRECT_URI` 是项目配置名，分别映射
    到 Skill 中的官方参数 `app_id` 与 `redirect_uri`。官方明确指定的
    `ZHIHU_OAUTH_APP_KEY` 与 `ZHIHU_ACCESS_SECRET` 保持原名。
    """

    app_id: str = ""
    app_key: str = ""
    redirect_uri: str = ""
    access_secret: str = ""
    cookie_secure: bool = False

    @classmethod
    def from_env(cls) -> "ZhihuConfig":
        return cls(
            app_id=os.getenv("ZHIHU_OAUTH_APP_ID", "").strip(),
            app_key=os.getenv("ZHIHU_OAUTH_APP_KEY", "").strip(),
            redirect_uri=(
                os.getenv("ZHIHU_OAUTH_REDIRECT_URI")
                or os.getenv("ZHIHU_REDIRECT_URI", "")
            ).strip(),
            access_secret=os.getenv("ZHIHU_ACCESS_SECRET", "").strip(),
            cookie_secure=_env_bool("ZHIHU_COOKIE_SECURE", False),
        )

    def missing_oauth_fields(self) -> list[str]:
        missing: list[str] = []
        if not self.app_id:
            missing.append("ZHIHU_OAUTH_APP_ID")
        if not self.app_key:
            missing.append("ZHIHU_OAUTH_APP_KEY")
        if not self.redirect_uri:
            missing.append("ZHIHU_OAUTH_REDIRECT_URI")
        return missing

    def missing_user_api_fields(self) -> list[str]:
        missing = self.missing_oauth_fields()
        if not self.access_secret:
            missing.append("ZHIHU_ACCESS_SECRET")
        return missing


class ZhihuServiceError(RuntimeError):
    """不包含凭证或上游响应正文的安全错误。"""

    def __init__(self, code: str, public_message: str, status_code: int = 502):
        super().__init__(public_message)
        self.code = code
        self.public_message = public_message
        self.status_code = status_code


def _decode_json(body: bytes) -> Any:
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ZhihuServiceError(
            "ZHIHU_INVALID_JSON",
            "知乎服务返回了无法解析的 JSON。",
        ) from exc


def _request_json(
    method: str,
    url: str,
    *,
    headers: Mapping[str, str],
    body: bytes | None = None,
    timeout: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
) -> Any:
    request = Request(url, data=body, headers=dict(headers), method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            return _decode_json(response.read())
    except HTTPError as exc:
        # 不读取/转发上游正文，避免把 token、内部诊断或用户数据回显到前端。
        status = int(exc.code) if isinstance(exc.code, int) else 502
        raise ZhihuServiceError(
            "ZHIHU_HTTP_ERROR",
            f"知乎服务请求失败（HTTP {status}）。",
            status_code=status,
        ) from exc
    except (TimeoutError, URLError, OSError) as exc:
        raise ZhihuServiceError(
            "ZHIHU_NETWORK_ERROR",
            "无法连接知乎服务，请稍后重试。",
            status_code=502,
        ) from exc


JsonPost = Callable[[str, bytes, Mapping[str, str], float], Any]
JsonGet = Callable[[str, Mapping[str, str], Mapping[str, str], float], Any]


def _default_post_json(
    url: str,
    body: bytes,
    headers: Mapping[str, str],
    timeout: float,
) -> Any:
    return _request_json("POST", url, headers=headers, body=body, timeout=timeout)


def _default_get_json(
    url: str,
    params: Mapping[str, str],
    headers: Mapping[str, str],
    timeout: float,
) -> Any:
    query = urlencode(dict(params))
    request_url = f"{url}?{query}" if query else url
    return _request_json("GET", request_url, headers=headers, timeout=timeout)


@dataclass(frozen=True, slots=True)
class OAuthToken:
    access_token: str
    token_type: str
    expires_in: int


@dataclass(frozen=True, slots=True)
class ZhihuUserProfile:
    uid: str
    hash_id: str | None
    fullname: str | None
    headline: str | None
    description: str | None
    avatar_path: str | None

    def to_public_dict(self) -> dict[str, str | None]:
        return {
            "uid": self.uid,
            "hash_id": self.hash_id,
            "fullname": self.fullname,
            "headline": self.headline,
            "description": self.description,
            "avatar_path": self.avatar_path,
        }


class ZhihuApiClient:
    """知乎 OAuth、用户数据和黑客松内容的协议适配层。"""

    def __init__(
        self,
        *,
        post_json: JsonPost | None = None,
        get_json: JsonGet | None = None,
    ) -> None:
        self._post_json = post_json or _default_post_json
        self._get_json = get_json or _default_get_json

    @staticmethod
    def authorization_url(config: ZhihuConfig, state: str | None = None) -> str:
        params = {
            "redirect_uri": config.redirect_uri,
            "app_id": config.app_id,
            "response_type": "code",
        }
        if state:
            # Skill 允许发出 state；回调是否稳定返回由平台确认后决定。
            params["state"] = state
        return f"{ZHIHU_OAUTH_AUTHORIZE_URL}?{urlencode(params)}"

    def exchange_code(self, config: ZhihuConfig, authorization_code: str) -> OAuthToken:
        if not authorization_code:
            raise ZhihuServiceError(
                "OAUTH_CODE_MISSING",
                "知乎 OAuth 回调缺少 authorization_code。",
                status_code=400,
            )

        form = urlencode(
            {
                "app_id": config.app_id,
                "app_key": config.app_key,
                "grant_type": "authorization_code",
                "redirect_uri": config.redirect_uri,
                # Skill 明确要求 token 接口使用 code 字段。
                "code": authorization_code,
            }
        ).encode("utf-8")
        payload = self._post_json(
            ZHIHU_OAUTH_TOKEN_URL,
            form,
            {"Content-Type": "application/x-www-form-urlencoded"},
            DEFAULT_HTTP_TIMEOUT_SECONDS,
        )

        if not isinstance(payload, dict):
            raise ZhihuServiceError(
                "OAUTH_TOKEN_RESPONSE_INVALID",
                "知乎 OAuth Token 响应格式无效。",
            )

        access_token = payload.get("access_token")
        expires_in = payload.get("expires_in")
        token_type = payload.get("token_type", "Bearer")
        if not isinstance(access_token, str) or not access_token.strip():
            # Skill 要求优先以 access_token 是否存在判断交换成功。
            raise ZhihuServiceError(
                "OAUTH_TOKEN_EXCHANGE_FAILED",
                "知乎 OAuth Token 交换未返回 access_token。",
            )
        if isinstance(expires_in, bool) or not isinstance(expires_in, int) or expires_in <= 0:
            raise ZhihuServiceError(
                "OAUTH_TOKEN_EXPIRY_INVALID",
                "知乎 OAuth Token 未返回有效的 expires_in。",
            )
        if not isinstance(token_type, str) or not token_type.strip():
            token_type = "Bearer"

        return OAuthToken(
            access_token=access_token.strip(),
            token_type=token_type.strip(),
            expires_in=expires_in,
        )

    def get_user_profile(self, oauth_access_token: str) -> ZhihuUserProfile:
        if not oauth_access_token:
            raise ZhihuServiceError(
                "OAUTH_TOKEN_MISSING",
                "无法读取知乎用户身份。",
                status_code=401,
            )

        payload = self._get_json(
            ZHIHU_USER_PROFILE_URL,
            {},
            {
                "Authorization": f"Bearer {oauth_access_token}",
                "Accept": "application/json",
            },
            DEFAULT_HTTP_TIMEOUT_SECONDS,
        )
        if not isinstance(payload, dict):
            raise ZhihuServiceError(
                "OAUTH_USER_RESPONSE_INVALID",
                "知乎用户身份响应格式无效。",
            )

        source: Mapping[str, Any] = payload
        for key in ("data", "Data", "user"):
            candidate = payload.get(key)
            if isinstance(candidate, dict):
                source = candidate
                break

        uid = source.get("uid")
        if isinstance(uid, bool) or not isinstance(uid, (int, str)):
            raise ZhihuServiceError(
                "OAUTH_USER_ID_INVALID",
                "知乎用户身份缺少有效 uid。",
            )
        uid_text = str(uid).strip()
        if not uid_text:
            raise ZhihuServiceError(
                "OAUTH_USER_ID_INVALID",
                "知乎用户身份缺少有效 uid。",
            )

        def optional_text(name: str) -> str | None:
            value = source.get(name)
            return value.strip() if isinstance(value, str) and value.strip() else None

        return ZhihuUserProfile(
            uid=uid_text,
            hash_id=optional_text("hash_id"),
            fullname=optional_text("fullname"),
            headline=optional_text("headline"),
            description=optional_text("description"),
            avatar_path=optional_text("avatar_path"),
        )

    def get_user_contents(
        self,
        config: ZhihuConfig,
        oauth_access_token: str,
        *,
        limit: int = 1,
    ) -> Any:
        if limit < 1 or limit > 50:
            raise ZhihuServiceError(
                "USER_API_LIMIT_INVALID",
                "用户内容请求的 limit 必须在 1-50 之间。",
                status_code=400,
            )

        headers = {
            "Authorization": f"Bearer {config.access_secret}",
            "X-OAuth-Token": oauth_access_token,
            "X-Request-Timestamp": str(int(time.time())),
            "Content-Type": "application/json",
        }
        return self._get_json(
            ZHIHU_USER_CONTENTS_URL,
            {
                "ContentType": "all",
                "Offset": "0",
                "Limit": str(limit),
            },
            headers,
            DEFAULT_HTTP_TIMEOUT_SECONDS,
        )

    @staticmethod
    def _work_path(kind: str, work_id: str) -> str:
        if not work_id or any(char in work_id for char in "/?#\r\n"):
            raise ZhihuServiceError(
                "HACKATHON_WORK_ID_INVALID",
                "知乎黑客松内容 ID 无效。",
                status_code=400,
            )
        return f"{ZHIHU_HACKATHON_API_BASE}/{kind}/{quote(work_id, safe='')}"

    def list_story(self) -> Any:
        return self._get_json(
            f"{ZHIHU_HACKATHON_API_BASE}/story/list",
            {},
            {"Accept": "application/json"},
            DEFAULT_HTTP_TIMEOUT_SECONDS,
        )

    def get_story(self, work_id: str) -> Any:
        return self._get_json(
            self._work_path("story", work_id),
            {},
            {"Accept": "application/json"},
            DEFAULT_HTTP_TIMEOUT_SECONDS,
        )

    def list_knowledge(self) -> Any:
        return self._get_json(
            f"{ZHIHU_HACKATHON_API_BASE}/knowledge/list",
            {},
            {"Accept": "application/json"},
            DEFAULT_HTTP_TIMEOUT_SECONDS,
        )

    def get_knowledge(self, work_id: str) -> Any:
        return self._get_json(
            self._work_path("knowledge", work_id),
            {},
            {"Accept": "application/json"},
            DEFAULT_HTTP_TIMEOUT_SECONDS,
        )


@dataclass(frozen=True, slots=True)
class PendingOAuthState:
    created_at: float


class OneTimeOAuthStateStore:
    """单进程、一次性 state 存储；多副本部署前需要共享存储。"""

    def __init__(self, ttl_seconds: int = OAUTH_STATE_TTL_SECONDS) -> None:
        self._ttl_seconds = ttl_seconds
        self._states: dict[str, PendingOAuthState] = {}
        self._lock = threading.Lock()

    def _prune(self, now: float) -> None:
        expired = [
            value
            for value, pending in self._states.items()
            if now - pending.created_at > self._ttl_seconds
        ]
        for value in expired:
            self._states.pop(value, None)

    def issue(self) -> str:
        value = secrets.token_urlsafe(32)
        with self._lock:
            now = time.time()
            self._prune(now)
            self._states[value] = PendingOAuthState(created_at=now)
        return value

    def consume(self, value: str) -> bool:
        if not value:
            return False
        with self._lock:
            now = time.time()
            self._prune(now)
            pending = self._states.pop(value, None)
        return pending is not None and now - pending.created_at <= self._ttl_seconds


@dataclass(frozen=True, slots=True)
class ServerOAuthSession:
    access_token: str
    token_type: str
    user: ZhihuUserProfile
    created_at: float
    expires_at: float

    def is_expired(self, now: float | None = None) -> bool:
        return (now if now is not None else time.time()) >= self.expires_at


class OAuthSessionStore:
    """服务端 OAuth session；不把 token 序列化到浏览器。"""

    def __init__(self) -> None:
        self._sessions: dict[str, ServerOAuthSession] = {}
        self._lock = threading.Lock()

    def create(
        self,
        token: OAuthToken,
        user: ZhihuUserProfile,
    ) -> tuple[str, ServerOAuthSession]:
        now = time.time()
        session = ServerOAuthSession(
            access_token=token.access_token,
            token_type=token.token_type,
            user=user,
            created_at=now,
            expires_at=now + token.expires_in,
        )
        session_id = secrets.token_urlsafe(32)
        with self._lock:
            self._sessions[session_id] = session
        return session_id, session

    def get(self, session_id: str | None) -> ServerOAuthSession | None:
        if not session_id:
            return None
        with self._lock:
            session = self._sessions.get(session_id)
            if session is not None and session.is_expired():
                self._sessions.pop(session_id, None)
                return None
            return session

    def delete(self, session_id: str | None) -> None:
        if not session_id:
            return
        with self._lock:
            self._sessions.pop(session_id, None)
