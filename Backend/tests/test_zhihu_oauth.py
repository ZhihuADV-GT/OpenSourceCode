from __future__ import annotations

import os
import time
import unittest
from http.cookies import SimpleCookie
from unittest.mock import patch
from urllib.parse import parse_qs, parse_qsl, urlsplit

from fastapi import HTTPException

from game.api.zhihu_service import (
    ZHIHU_OAUTH_AUTHORIZE_URL,
    ZHIHU_OAUTH_TOKEN_URL,
    ZHIHU_USER_PROFILE_URL,
    OAUTH_STATE_COOKIE_NAME,
    OAUTH_STATE_COOKIE_PATH,
    ZhihuApiClient,
    ZhihuConfig,
    OAuthSessionStore,
    OAuthToken,
    OneTimeOAuthStateStore,
    PendingOAuthState,
    ZhihuServiceError,
    ZhihuUserProfile,
)
from game.api import api as api_module


def make_request(*, query: str = "", cookie: str = ""):
    headers = []
    if cookie:
        headers.append((b"cookie", cookie.encode("ascii")))
    return api_module.Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/test",
            "query_string": query.encode("utf-8"),
            "headers": headers,
            "client": ("test", 1234),
            "server": ("test", 80),
            "scheme": "http",
        }
    )


def response_set_cookie_headers(response) -> list[str]:
    return [
        value.decode("latin-1")
        for key, value in response.raw_headers
        if key.lower() == b"set-cookie"
    ]


class ZhihuOAuthContractTests(unittest.TestCase):
    def configured_env(self) -> dict[str, str]:
        return {
            "ZHIHU_OAUTH_APP_ID": "demo-app-id",
            "ZHIHU_OAUTH_APP_KEY": "demo-app-key",
            "ZHIHU_OAUTH_REDIRECT_URI": "http://localhost:5173/api/auth/zhihu/callback",
            "ZHIHU_ACCESS_SECRET": "open-platform-secret",
            "ZHIHU_COOKIE_SECURE": "false",
        }

    def sample_profile(self, uid: str = "9223372036854775807") -> ZhihuUserProfile:
        return ZhihuUserProfile(
            uid=uid,
            hash_id="demo-hash-id",
            fullname="测试用户",
            headline="测试签名",
            description="测试简介",
            avatar_path="https://example.com/avatar.png",
        )

    def test_config_reads_official_redirect_env_name(self) -> None:
        with patch.dict(os.environ, self.configured_env(), clear=True):
            config = ZhihuConfig.from_env()

        self.assertEqual(
            config.redirect_uri,
            "http://localhost:5173/api/auth/zhihu/callback",
        )
        self.assertEqual(config.missing_oauth_fields(), [])

    def test_authorization_url_uses_skill_fields(self) -> None:
        config = ZhihuConfig(
            app_id="demo-app-id",
            app_key="demo-app-key",
            redirect_uri="http://localhost:3000/api/auth/zhihu/callback",
        )

        url = ZhihuApiClient.authorization_url(config, "state-demo")
        parsed = urlsplit(url)

        self.assertEqual(f"{parsed.scheme}://{parsed.netloc}{parsed.path}", ZHIHU_OAUTH_AUTHORIZE_URL)
        self.assertEqual(
            parse_qs(parsed.query),
            {
                "redirect_uri": [config.redirect_uri],
                "app_id": [config.app_id],
                "response_type": ["code"],
                "state": ["state-demo"],
            },
        )

    def test_exchange_uses_authorization_code_callback_as_code_form_field(self) -> None:
        captured: dict[str, object] = {}

        def fake_post(url: str, body: bytes, headers, timeout: float):
            captured["url"] = url
            captured["body"] = body.decode("utf-8")
            captured["headers"] = dict(headers)
            captured["timeout"] = timeout
            return {
                "access_token": "oauth-token-for-test",
                "token_type": "Bearer",
                "expires_in": 3600,
            }

        config = ZhihuConfig(
            app_id="demo-app-id",
            app_key="demo-app-key",
            redirect_uri="http://localhost/callback",
        )
        token = ZhihuApiClient(post_json=fake_post).exchange_code(
            config,
            "callback-authorization-code",
        )

        self.assertEqual(captured["url"], ZHIHU_OAUTH_TOKEN_URL)
        self.assertEqual(
            dict(parse_qsl(str(captured["body"]))),
            {
                "app_id": "demo-app-id",
                "app_key": "demo-app-key",
                "grant_type": "authorization_code",
                "redirect_uri": "http://localhost/callback",
                "code": "callback-authorization-code",
            },
        )
        self.assertEqual(captured["headers"], {"Content-Type": "application/x-www-form-urlencoded"})
        self.assertEqual(token.expires_in, 3600)

    def test_token_exchange_rejects_missing_access_token(self) -> None:
        client = ZhihuApiClient(post_json=lambda *args: {"expires_in": 3600})
        config = ZhihuConfig(
            app_id="demo-app-id",
            app_key="demo-app-key",
            redirect_uri="http://localhost:5173/api/auth/zhihu/callback",
        )

        with self.assertRaises(ZhihuServiceError) as raised:
            client.exchange_code(config, "callback-code")

        self.assertEqual(raised.exception.code, "OAUTH_TOKEN_EXCHANGE_FAILED")
        self.assertNotIn("oauth-token-for-test", raised.exception.public_message)

    def test_token_exchange_rejects_invalid_expires_in(self) -> None:
        config = ZhihuConfig(
            app_id="demo-app-id",
            app_key="demo-app-key",
            redirect_uri="http://localhost:5173/api/auth/zhihu/callback",
        )
        for invalid_expires in (None, 0, -1, "3600", True):
            with self.subTest(invalid_expires=invalid_expires):
                client = ZhihuApiClient(
                    post_json=lambda *args, invalid_expires=invalid_expires: {
                        "access_token": "oauth-token-for-test",
                        "expires_in": invalid_expires,
                    }
                )
                with self.assertRaises(ZhihuServiceError) as raised:
                    client.exchange_code(config, "callback-code")
                self.assertEqual(raised.exception.code, "OAUTH_TOKEN_EXPIRY_INVALID")

    def test_user_profile_uses_oauth_bearer_and_preserves_int64_uid(self) -> None:
        captured: dict[str, object] = {}

        def fake_get(url: str, params, headers, timeout: float):
            captured["url"] = url
            captured["params"] = dict(params)
            captured["headers"] = dict(headers)
            return {
                "uid": 9223372036854775807,
                "hash_id": "demo-hash-id",
                "fullname": "测试用户",
                "headline": "测试签名",
                "description": "测试简介",
                "avatar_path": "https://example.com/avatar.png",
            }

        profile = ZhihuApiClient(get_json=fake_get).get_user_profile("oauth-user-token")

        self.assertEqual(captured["url"], ZHIHU_USER_PROFILE_URL)
        self.assertEqual(captured["params"], {})
        self.assertEqual(
            captured["headers"],
            {
                "Authorization": "Bearer oauth-user-token",
                "Accept": "application/json",
            },
        )
        self.assertEqual(profile.uid, "9223372036854775807")
        self.assertIsInstance(profile.uid, str)
        self.assertEqual(profile.fullname, "测试用户")

    def test_user_profile_rejects_float_uid_to_avoid_precision_loss(self) -> None:
        client = ZhihuApiClient(get_json=lambda *args: {"uid": 9.223372036854776e18})

        with self.assertRaises(ZhihuServiceError) as raised:
            client.get_user_profile("oauth-user-token")

        self.assertEqual(raised.exception.code, "OAUTH_USER_ID_INVALID")

    def test_user_contents_uses_two_distinct_auth_headers(self) -> None:
        captured: dict[str, object] = {}

        def fake_get(url: str, params, headers, timeout: float):
            captured["url"] = url
            captured["params"] = dict(params)
            captured["headers"] = dict(headers)
            return {"Code": 0, "Message": "success", "Data": {"Items": []}}

        config = ZhihuConfig(access_secret="open-platform-secret")
        result = ZhihuApiClient(get_json=fake_get).get_user_contents(
            config,
            "oauth-user-token",
            limit=1,
        )

        self.assertEqual(result["Code"], 0)
        self.assertEqual(captured["params"], {"ContentType": "all", "Offset": "0", "Limit": "1"})
        headers = captured["headers"]
        self.assertEqual(headers["Authorization"], "Bearer open-platform-secret")
        self.assertEqual(headers["X-OAuth-Token"], "oauth-user-token")
        self.assertNotIn("app_key", headers)

    def test_hackathon_detail_rejects_path_injection(self) -> None:
        client = ZhihuApiClient(get_json=lambda *args: {})
        with self.assertRaises(Exception):
            client.get_story("123/other")

    def test_state_is_one_time(self) -> None:
        store = OneTimeOAuthStateStore()
        state = store.issue()
        self.assertTrue(store.consume(state))
        self.assertFalse(store.consume(state))

    def test_state_values_are_cryptographically_random(self) -> None:
        store = OneTimeOAuthStateStore()
        first = store.issue()
        second = store.issue()

        self.assertNotEqual(first, second)
        self.assertGreaterEqual(len(first), 40)
        self.assertGreaterEqual(len(second), 40)

    def test_session_store_expires_and_does_not_expose_token_id(self) -> None:
        store = OAuthSessionStore()
        session_id, session = store.create(
            OAuthToken("oauth-token-for-test", "Bearer", 1),
            self.sample_profile(),
        )
        self.assertNotEqual(session_id, session.access_token)
        self.assertEqual(session.user.uid, "9223372036854775807")
        self.assertEqual(store.get(session_id), session)
        self.assertTrue(session.is_expired(now=session.expires_at))

    def test_login_generates_state_and_browser_cookie(self) -> None:
        with patch.dict(os.environ, self.configured_env(), clear=False):
            response = api_module.zhihu_login()

        self.assertEqual(response.status_code, 302)
        cookie_header = response.headers["set-cookie"]
        self.assertIn(f"{OAUTH_STATE_COOKIE_NAME}=", cookie_header)
        self.assertIn("HttpOnly", cookie_header)
        self.assertIn("SameSite=lax", cookie_header)
        self.assertIn("Max-Age=600", cookie_header)
        cookie = SimpleCookie()
        cookie.load(cookie_header)
        browser_state = cookie[OAUTH_STATE_COOKIE_NAME].value
        query_state = parse_qs(urlsplit(response.headers["location"]).query)["state"][0]
        self.assertTrue(browser_state)
        self.assertEqual(browser_state, query_state)
        self.assertIn(f"Path={OAUTH_STATE_COOKIE_PATH}", cookie_header)

    def test_unconfigured_login_returns_safe_not_configured_error(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(HTTPException) as raised:
                api_module.zhihu_login()

        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(raised.exception.detail["code"], "ZHIHU_NOT_CONFIGURED")

    def test_callback_rejects_missing_browser_state_cookie(self) -> None:
        state = api_module._zhihu_state_store.issue()
        with patch.dict(os.environ, self.configured_env(), clear=False):
            response = api_module.zhihu_callback(
                make_request(query=f"authorization_code=callback-code&state={state}")
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("OAUTH_BROWSER_STATE_MISSING", response.body.decode("utf-8"))
        self.assertIn(f"{OAUTH_STATE_COOKIE_NAME}=", response.headers["set-cookie"])

    def test_callback_rejects_mismatched_browser_state(self) -> None:
        callback_state = api_module._zhihu_state_store.issue()
        browser_state = api_module._zhihu_state_store.issue()
        with patch.dict(os.environ, self.configured_env(), clear=False):
            response = api_module.zhihu_callback(
                make_request(
                    query=f"authorization_code=callback-code&state={callback_state}",
                    cookie=f"{OAUTH_STATE_COOKIE_NAME}={browser_state}",
                )
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("OAUTH_STATE_MISMATCH", response.body.decode("utf-8"))

    def test_callback_rejects_expired_state(self) -> None:
        state_store = OneTimeOAuthStateStore(ttl_seconds=1)
        state = state_store.issue()
        state_store._states[state] = PendingOAuthState(created_at=time.time() - 2)
        with patch.dict(os.environ, self.configured_env(), clear=False), patch.object(
            api_module, "_zhihu_state_store", state_store
        ):
            response = api_module.zhihu_callback(
                make_request(
                    query=f"authorization_code=callback-code&state={state}",
                    cookie=f"{OAUTH_STATE_COOKIE_NAME}={state}",
                )
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("OAUTH_STATE_INVALID", response.body.decode("utf-8"))

    def test_callback_rejects_already_consumed_state(self) -> None:
        state = api_module._zhihu_state_store.issue()

        class FakeClient:
            @staticmethod
            def exchange_code(config, authorization_code):
                return OAuthToken("oauth-token-for-test", "Bearer", 3600)

            @staticmethod
            def get_user_profile(oauth_access_token):
                return self.sample_profile()

        request = make_request(
            query=f"authorization_code=callback-code&state={state}",
            cookie=f"{OAUTH_STATE_COOKIE_NAME}={state}",
        )
        with patch.dict(os.environ, self.configured_env(), clear=False), patch.object(
            api_module, "_zhihu_client", FakeClient()
        ):
            first = api_module.zhihu_callback(request)
            second = api_module.zhihu_callback(request)

        self.assertEqual(first.status_code, 303)
        self.assertEqual(second.status_code, 400)
        self.assertIn("OAUTH_STATE_INVALID", second.body.decode("utf-8"))

    def test_unauthed_test_endpoint_requires_login(self) -> None:
        response = api_module.Response()
        with self.assertRaises(HTTPException) as raised:
            api_module.zhihu_test(make_request(), response)

        self.assertEqual(raised.exception.status_code, 401)
        self.assertEqual(raised.exception.detail["code"], "ZHIHU_LOGIN_REQUIRED")

    def test_callback_without_state_fails_closed(self) -> None:
        with patch.dict(
            os.environ,
            self.configured_env(),
            clear=False,
        ):
            response = api_module.zhihu_callback(
                make_request(query="authorization_code=callback-code")
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("OAUTH_STATE_MISSING", response.body.decode("utf-8"))

    def test_callback_does_not_create_session_when_profile_fetch_fails(self) -> None:
        class FakeClient:
            @staticmethod
            def exchange_code(config, authorization_code):
                return OAuthToken("oauth-token-must-not-leak", "Bearer", 3600)

            @staticmethod
            def get_user_profile(oauth_access_token):
                raise ZhihuServiceError(
                    "OAUTH_USER_RESPONSE_INVALID",
                    "知乎用户身份响应格式无效。",
                )

        state = api_module._zhihu_state_store.issue()
        with patch.dict(
            os.environ,
            self.configured_env(),
            clear=False,
        ), patch.object(api_module, "_zhihu_client", FakeClient()):
            response = api_module.zhihu_callback(
                make_request(
                    query=f"authorization_code=callback-code&state={state}",
                    cookie=f"{OAUTH_STATE_COOKIE_NAME}={state}",
                )
            )

        self.assertEqual(response.status_code, 502)
        response_text = response.body.decode("utf-8")
        self.assertIn("OAUTH_USER_RESPONSE_INVALID", response_text)
        self.assertNotIn("oauth-token-must-not-leak", response_text)
        cookies = "\n".join(response_set_cookie_headers(response))
        self.assertNotIn(f"{api_module.SESSION_COOKIE_NAME}=", cookies)

    def test_mock_callback_creates_cookie_only_for_server_session(self) -> None:
        class FakeClient:
            @staticmethod
            def exchange_code(config, authorization_code):
                self.assertEqual(authorization_code, "callback-code")
                return OAuthToken("oauth-token-not-in-cookie", "Bearer", 3600)

            @staticmethod
            def get_user_profile(oauth_access_token):
                self.assertEqual(oauth_access_token, "oauth-token-not-in-cookie")
                return self.sample_profile()

            @staticmethod
            def get_user_contents(config, oauth_access_token, *, limit):
                self.assertEqual(oauth_access_token, "oauth-token-not-in-cookie")
                self.assertEqual(limit, 1)
                return {
                    "Code": 0,
                    "Message": "success",
                    "access_token": "oauth-token-must-not-return",
                    "Data": {"Items": [], "app_key": "app-key-must-not-return"},
                }

        state = api_module._zhihu_state_store.issue()
        query = f"authorization_code=callback-code&state={state}"
        with patch.dict(
            os.environ,
            self.configured_env(),
            clear=False,
        ), patch.object(api_module, "_zhihu_client", FakeClient()):
            redirect = api_module.zhihu_callback(
                make_request(
                    query=query,
                    cookie=f"{OAUTH_STATE_COOKIE_NAME}={state}",
                )
            )

            cookie = SimpleCookie()
            set_cookie_headers = response_set_cookie_headers(redirect)
            for set_cookie_header in set_cookie_headers:
                cookie.load(set_cookie_header)
            session_id = cookie[api_module.SESSION_COOKIE_NAME].value
            self.assertTrue(session_id)
            all_cookie_headers = "\n".join(set_cookie_headers)
            self.assertNotIn("oauth-token-not-in-cookie", all_cookie_headers)
            self.assertIn(f"{OAUTH_STATE_COOKIE_NAME}=", all_cookie_headers)
            self.assertIn("Max-Age=3600", all_cookie_headers)
            self.assertIn("HttpOnly", all_cookie_headers)
            self.assertIn("SameSite=lax", all_cookie_headers)
            self.assertIn("Path=/", all_cookie_headers)

            status_response = api_module.Response()
            status = api_module.zhihu_auth_status(
                make_request(cookie=f"{api_module.SESSION_COOKIE_NAME}={session_id}"),
                status_response,
            )
            self.assertTrue(status["authenticated"])
            self.assertEqual(status["user"]["uid"], "9223372036854775807")
            self.assertEqual(status["user"]["fullname"], "测试用户")
            self.assertNotIn("access_token", str(status))

            result = api_module.zhihu_test(
                make_request(cookie=f"{api_module.SESSION_COOKIE_NAME}={session_id}"),
                api_module.Response(),
            )
            self.assertTrue(result["ok"])
            result_text = str(result)
            self.assertNotIn("oauth-token-must-not-return", result_text)
            self.assertNotIn("app-key-must-not-return", result_text)

    def test_logout_deletes_server_session_and_cookie(self) -> None:
        store = OAuthSessionStore()
        session_id, _ = store.create(
            OAuthToken("oauth-token-for-test", "Bearer", 3600),
            self.sample_profile(),
        )
        with patch.object(api_module, "_zhihu_session_store", store):
            response = api_module.Response()
            result = api_module.zhihu_logout(
                make_request(cookie=f"{api_module.SESSION_COOKIE_NAME}={session_id}"),
                response,
            )

        self.assertFalse(result["authenticated"])
        self.assertIsNone(store.get(session_id))
        self.assertIn(f"{api_module.SESSION_COOKIE_NAME}=", response.headers["set-cookie"])
        self.assertIn("Max-Age=0", response.headers["set-cookie"])

    def test_expired_session_reports_unauthenticated_and_clears_cookie(self) -> None:
        store = OAuthSessionStore()
        session_id, _ = store.create(
            OAuthToken("oauth-token-for-test", "Bearer", -1),
            self.sample_profile(),
        )
        with patch.dict(os.environ, self.configured_env(), clear=False), patch.object(
            api_module, "_zhihu_session_store", store
        ):
            response = api_module.Response()
            result = api_module.zhihu_auth_status(
                make_request(cookie=f"{api_module.SESSION_COOKIE_NAME}={session_id}"),
                response,
            )

        self.assertFalse(result["authenticated"])
        self.assertIn("Max-Age=0", response.headers["set-cookie"])

    def test_upstream_error_does_not_leak_body_or_token(self) -> None:
        store = OAuthSessionStore()
        session_id, _ = store.create(
            OAuthToken("oauth-token-for-test", "Bearer", 3600),
            self.sample_profile(),
        )

        class FakeClient:
            @staticmethod
            def get_user_contents(config, oauth_access_token, *, limit):
                raise ZhihuServiceError(
                    "ZHIHU_HTTP_ERROR",
                    "知乎服务请求失败（HTTP 401）。",
                    status_code=401,
                )

        with patch.dict(os.environ, self.configured_env(), clear=False), patch.object(
            api_module, "_zhihu_session_store", store
        ), patch.object(api_module, "_zhihu_client", FakeClient()):
            with self.assertRaises(HTTPException) as raised:
                api_module.zhihu_test(
                    make_request(cookie=f"{api_module.SESSION_COOKIE_NAME}={session_id}"),
                    api_module.Response(),
                )

        self.assertEqual(raised.exception.status_code, 401)
        self.assertEqual(raised.exception.detail["code"], "ZHIHU_OAUTH_SESSION_INVALID")
        self.assertNotIn("oauth-token-for-test", str(raised.exception.detail))
        self.assertNotIn("upstream-secret-body", str(raised.exception.detail))


if __name__ == "__main__":
    unittest.main()
