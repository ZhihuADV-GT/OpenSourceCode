"""
看山 AI 服务层

职责：
- 封装通义千问 HTTP API 调用（点评 + 聊天 + 局间剧情）
- 为 /api/ai/comment、/api/ai/chat、/api/ai/story 提供业务逻辑
- API 异常时返回 None，由调用方使用硬编码消息降级
"""

from __future__ import annotations

import json
import random
import re
import time

import requests

from game.api.llm_config import (
    TONGYI_API_BASE_URL,
    TONGYI_API_KEY,
    TONGYI_MODEL_CHAT,
    TONGYI_MODEL_STORY,
    TONGYI_MODEL_HINT,
    TONGYI_MODEL_DYNAMIC_CARD,
    TONGYI_MODEL_ANNOTATE,
    TONGYI_TIMEOUT_COMMENT,
    TONGYI_TIMEOUT_CHAT,
    TONGYI_TIMEOUT_STORY,
    TONGYI_TIMEOUT_HINT,
    STORY_MAX_TOKENS,
    STORY_TEMPERATURE,
    HINT_MAX_TOKENS,
    HINT_TEMPERATURE,
    BACKUP_LLM_API_BASE_URL,
    BACKUP_LLM_API_KEY,
    BACKUP_MODEL_CHAT,
    BACKUP_MODEL_STORY,
    BACKUP_MODEL_HINT,
    BACKUP_MODEL_DYNAMIC_CARD,
    BACKUP_MODEL_ANNOTATE,
    DEEPSEEK_API_BASE_URL,
    DEEPSEEK_API_KEY,
    DEEPSEEK_MODEL_CHAT,
    DEEPSEEK_MODEL_STORY,
    DEEPSEEK_MODEL_HINT,
    DEEPSEEK_MODEL_DYNAMIC_CARD,
    DEEPSEEK_MODEL_ANNOTATE,
)
from game.api.llm_prompt import (
    COMMENT_SYSTEM_PROMPT,
    EVENT_DESCRIPTIONS,
    FALLBACK_COMMENTS,
    CHAT_SYSTEM_PROMPT,
    FALLBACK_CHAT_REPLIES,
    STORY_SYSTEM_PROMPT,
    STORY_USER_PROMPT_TEMPLATE,
    STORY_SPEAKER_PROFILES,
    STORY_NPC_BY_QUADRANT,
    STORY_QUADRANT_NAMES,
    STORY_DIRECTION_LABELS,
    QUADRANT_FLAVOR_HINTS,
    STORY_MIN_LINES,
    STORY_MAX_LINES,
    STORY_PLAYER_MAX_CHARS,
    STORY_LINE_MAX_CHARS,
    STORY_NPC_MIN_LINES,
    STORY_NPC_MAX_LINES,
    STORY_TARGET_MIN_LINES,
    HINT_DEEP_SYSTEM_PROMPT,
    HINT_DEEP_USER_TEMPLATE,
    FALLBACK_HINT_DEEP,
    COMPOSITION_HINT_SYSTEM_PROMPT,
    COMPOSITION_HINT_USER_TEMPLATE,
    FALLBACK_COMPOSITION_HINT_DEEP,
)


# ══════════════════════════════════════════════════════════
#  底层：通义千问调用（支持多模型 failover）
# ══════════════════════════════════════════════════════════


def _call_tongyi_single(
    url: str,
    headers: dict,
    system_prompt: str,
    user_prompt: str,
    model: str,
    max_tokens: int,
    temperature: float,
    timeout: int,
) -> str | None:
    """单次调用通义千问，返回生成的文本。

    成功 → str；额度耗尽 / 限流 / 服务端异常 / 解析失败 → None。
    网络超时由 requests.Timeout 抛出，交给 call_tongyi 的 failover 循环处理。
    """
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "enable_thinking": False,   # qwen3.5 默认开思考模式，关掉以控制延迟
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=timeout)

    # ── 非 200：先读响应体再判错误类型（不丢弃 body，避免排查盲区） ──
    if resp.status_code != 200:
        try:
            body = resp.json()
        except Exception:
            body = {"raw": resp.text[:200]}

        if resp.status_code == 403:
            code = body.get("code") or body.get("error", {}).get("code", "")
            msg = body.get("message") or body.get("error", {}).get("message", "")
            print(f"[ai_service] 模型 {model} 额度/权限错误 (403): {code} {msg}")
            return None
        if resp.status_code == 429:
            print(f"[ai_service] 模型 {model} 限流 (429)")
            return None
        if resp.status_code >= 500:
            print(f"[ai_service] 模型 {model} 服务端错误 ({resp.status_code})")
            return None

        # 其他 HTTP 错误（401 鉴权失败等）
        resp.raise_for_status()
        return None

    # ── 200 响应（OpenAI 兼容格式：choices[0].message.content） ─
    result = resp.json()

    try:
        return result["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError) as e:
        print(f"[ai_service] 模型 {model} 响应解析失败: {e}")
        return None


def _call_openai_single(
    url: str,
    headers: dict,
    system_prompt: str,
    user_prompt: str,
    model: str,
    max_tokens: int,
    temperature: float,
    timeout: int,
) -> str | None:
    """单次调用 OpenAI 兼容 API，返回生成的文本。

    与 _call_tongyi_single 的区别：
    - 请求路径为 /chat/completions
    - 响应从 choices[0].message.content 取值
    """
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=timeout)

    if resp.status_code != 200:
        try:
            body = resp.json()
        except Exception:
            body = {"raw": resp.text[:200]}

        if resp.status_code == 403:
            code = body.get("code") or body.get("error", {}).get("code", "")
            msg = body.get("message") or body.get("error", {}).get("message", "")
            print(f"[ai_service][backup] 模型 {model} 额度/权限错误 (403): {code} {msg}")
            return None
        if resp.status_code == 429:
            print(f"[ai_service][backup] 模型 {model} 限流 (429)")
            return None
        if resp.status_code >= 500:
            print(f"[ai_service][backup] 模型 {model} 服务端错误 ({resp.status_code})")
            return None

        resp.raise_for_status()
        return None

    result = resp.json()

    # OpenAI 兼容格式：choices[0].message.content
    try:
        return result["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError) as e:
        print(f"[ai_service][backup] 模型 {model} 响应解析失败: {e}")
        return None


def call_tongyi(
    system_prompt: str,
    user_prompt: str,
    *,
    model: str | list[str] | None = None,
    max_tokens: int = 120,
    temperature: float = 0.85,
    timeout: int = 10,
) -> str | None:
    """调用 LLM，返回生成的文本；异常时返回 None。

    两级 failover 机制：
    1. 模型级：在阿里云（DashScope）内按模型列表逐个尝试
    2. 提供商级：阿里云全部模型失败后，自动切换到备用提供商（OpenAI 兼容）

    整个 failover 链共享 timeout 秒作为总超时预算，防止逐个模型超时叠加。
    """
    if model is None:
        model = TONGYI_MODEL_CHAT
    models = model if isinstance(model, list) else [model]
    if not models:
        print("[ai_service] 模型列表为空，跳过调用")
        return None

    # ── 第 1 级：阿里云 DashScope（OpenAI 兼容格式） ──
    # TODO: 测试完毕后删除下面两行，恢复主链路
    _SKIP_PRIMARY = False
    if _SKIP_PRIMARY:
        models = []  # 清空主链路模型，直接跳备用提供商
        print("[ai_service] 主链路已临时禁用，直接使用备用提供商")

    url = f"{TONGYI_API_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {TONGYI_API_KEY}",
        "Content-Type": "application/json",
    }

    total_budget = float(timeout)
    deadline = time.monotonic() + total_budget

    for i, m in enumerate(models):
        remaining = deadline - time.monotonic()
        if remaining < 1:
            print(f"[ai_service] 阿里云总超时预算 {timeout}s 已耗尽（剩余 {remaining:.1f}s），"
                  f"已尝试 {i}/{len(models)} 个模型，停止 failover")
            break

        try:
            result = _call_tongyi_single(
                url, headers, system_prompt, user_prompt,
                m, max_tokens, temperature, int(remaining),
            )
            if result:
                print(f"[ai_service] ✓ 阿里云模型 [{m}] 成功")
                return result
        except requests.Timeout:
            print(f"[ai_service] 阿里云模型 {m} 超时，尝试下一个...")
            continue
        except Exception as e:
            print(f"[ai_service] 阿里云模型 {m} 异常: {e}，尝试下一个...")
            continue

        if i < len(models) - 1:
            print(f"[ai_service] 阿里云模型 {m} 失败，尝试下一个 ({i+2}/{len(models)})...")

    # ── 第 2 级：备用提供商（OpenAI 兼容） ──
    # TODO: 测试完毕后删除下面两行，恢复第一备用链路
    _SKIP_BACKUP = False
    if _SKIP_BACKUP:
        pass  # 跳过第一备用，直接进 DeepSeek
    elif BACKUP_LLM_API_KEY and BACKUP_LLM_API_BASE_URL:
        remaining = deadline - time.monotonic()
        if remaining > 0:
            print(f"[ai_service] 阿里云全部失败，切换到备用提供商 (剩余预算 {remaining:.1f}s)")
            backup_models = _get_backup_models(model)
            backup_url = f"{BACKUP_LLM_API_BASE_URL}/chat/completions"
            backup_headers = {
                "Authorization": f"Bearer {BACKUP_LLM_API_KEY}",
                "Content-Type": "application/json",
            }
            for j, bm in enumerate(backup_models):
                remaining = deadline - time.monotonic()
                if remaining < 1:
                    print(f"[ai_service][backup] 预算不足 1s（剩余 {remaining:.1f}s），跳过模型 {bm}")
                    break
                try:
                    result = _call_openai_single(
                        backup_url, backup_headers, system_prompt, user_prompt,
                        bm, max_tokens, temperature, int(remaining),
                    )
                    if result:
                        print(f"[ai_service] ✓ 备用提供商 failover 成功：模型 [{bm}]")
                        return result
                    print(f"[ai_service][backup] 模型 {bm} 返回空结果，尝试下一个...")
                except requests.Timeout:
                    print(f"[ai_service][backup] 模型 {bm} 超时，尝试下一个...")
                    continue
                except Exception as e:
                    print(f"[ai_service][backup] 模型 {bm} 异常: {e}，尝试下一个...")
                    continue
        else:
            print("[ai_service] 备用提供商跳过：超时预算已耗尽")
    else:
        print("[ai_service] 备用提供商未配置（BACKUP_LLM_API_KEY 为空），跳过")

    # ── 第 3 级：第二备用提供商（DeepSeek） ──
    if DEEPSEEK_API_KEY and DEEPSEEK_API_BASE_URL:
        remaining = deadline - time.monotonic()
        if remaining > 0:
            print(f"[ai_service] 备用提供商也失败，切换到 DeepSeek (剩余预算 {remaining:.1f}s)")
            deepseek_models = _get_deepseek_models(model)
            deepseek_url = f"{DEEPSEEK_API_BASE_URL}/v1/chat/completions"
            deepseek_headers = {
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json",
            }
            for k, dm in enumerate(deepseek_models):
                remaining = deadline - time.monotonic()
                if remaining < 1:
                    print(f"[ai_service][deepseek] 预算不足 1s（剩余 {remaining:.1f}s），跳过模型 {dm}")
                    break
                try:
                    result = _call_openai_single(
                        deepseek_url, deepseek_headers, system_prompt, user_prompt,
                        dm, max_tokens, temperature, int(remaining),
                    )
                    if result:
                        print(f"[ai_service] ✓ DeepSeek failover 成功：模型 [{dm}]")
                        return result
                    print(f"[ai_service][deepseek] 模型 {dm} 返回空结果，尝试下一个...")
                except requests.Timeout:
                    print(f"[ai_service][deepseek] 模型 {dm} 超时，尝试下一个...")
                    continue
                except Exception as e:
                    print(f"[ai_service][deepseek] 模型 {dm} 异常: {e}，尝试下一个...")
                    continue
        else:
            print("[ai_service] DeepSeek 跳过：超时预算已耗尽")
    else:
        print("[ai_service] DeepSeek 未配置（DEEPSEEK_API_KEY 为空），跳过")

    print(f"[ai_service] 所有提供商均失败，返回 None")
    return None


def _get_backup_models(primary_model) -> list[str]:
    """根据主链路类型选择对应的备用模型列表。"""
    # 通过比较引用判断是哪个业务链路
    if primary_model is TONGYI_MODEL_ANNOTATE:
        return BACKUP_MODEL_ANNOTATE
    if primary_model is TONGYI_MODEL_CHAT:
        return BACKUP_MODEL_CHAT
    if primary_model is TONGYI_MODEL_STORY:
        return BACKUP_MODEL_STORY
    if primary_model is TONGYI_MODEL_HINT:
        return BACKUP_MODEL_HINT
    if primary_model is TONGYI_MODEL_DYNAMIC_CARD:
        return BACKUP_MODEL_DYNAMIC_CARD
    # 默认使用 CHAT 备用模型
    return BACKUP_MODEL_CHAT


def _get_deepseek_models(primary_model) -> list[str]:
    """根据主链路类型选择对应的 DeepSeek 模型列表。"""
    if primary_model is TONGYI_MODEL_ANNOTATE:
        return DEEPSEEK_MODEL_ANNOTATE
    if primary_model is TONGYI_MODEL_CHAT:
        return DEEPSEEK_MODEL_CHAT
    if primary_model is TONGYI_MODEL_STORY:
        return DEEPSEEK_MODEL_STORY
    if primary_model is TONGYI_MODEL_HINT:
        return DEEPSEEK_MODEL_HINT
    if primary_model is TONGYI_MODEL_DYNAMIC_CARD:
        return DEEPSEEK_MODEL_DYNAMIC_CARD
    return DEEPSEEK_MODEL_CHAT


# ══════════════════════════════════════════════════════════
#  点评模块
# ══════════════════════════════════════════════════════════


def generate_comment(event_type: str, context: dict | None = None) -> str | None:
    """根据事件类型和游戏上下文生成一句话点评

    Returns:
        AI 生成的点评文本，失败时返回 None
    """
    event_desc = EVENT_DESCRIPTIONS.get(event_type, "玩家完成了一个操作")

    # 构建用户 prompt，注入上下文
    parts = [f"事件：{event_desc}"]
    if context:
        if context.get("text"):
            parts.append(f"划线文本片段：「{context['text'][:60]}」")
        if context.get("card_type"):
            parts.append(f"卡牌类型：{context['card_type']}")
        if context.get("vector"):
            parts.append(f"当前向量：{context['vector']}")

    user_prompt = "\n".join(parts) + "\n请给出一句简短点评："

    return call_tongyi(
        COMMENT_SYSTEM_PROMPT,
        user_prompt,
        max_tokens=60,
        temperature=0.9,
        timeout=TONGYI_TIMEOUT_COMMENT,
    )


# ── 点评降级 ────────────────────────────────────────


def fallback_comment(event_type: str) -> str:
    """降级：从 llm_prompt.py 消息池随机选取"""
    pool = FALLBACK_COMMENTS.get(event_type, FALLBACK_COMMENTS["card_place"])
    return random.choice(pool)


# ══════════════════════════════════════════════════════════
#  聊天模块
# ══════════════════════════════════════════════════════════


def generate_chat_reply(user_message: str, history: list[dict] | None = None) -> str | None:
    """根据玩家消息和对话历史生成 AI 回复

    Args:
        user_message: 玩家当前输入
        history: 对话历史 [{sender: "player"|"ai", text: "..."}, ...]

    Returns:
        AI 回复文本，失败时返回 None
    """
    # 构建对话历史上下文（最近 5 轮 = 10 条消息）
    history_text = ""
    if history:
        recent = history[-10:]
        lines = []
        for msg in recent:
            role = "玩家" if msg.get("sender") == "player" else "看山"
            lines.append(f"{role}：{msg.get('text', '')}")
        history_text = "最近对话记录：\n" + "\n".join(lines) + "\n\n"

    user_prompt = f"{history_text}玩家说：{user_message}\n请以看山的身份回复："

    return call_tongyi(
        CHAT_SYSTEM_PROMPT,
        user_prompt,
        max_tokens=150,
        temperature=0.85,
        timeout=TONGYI_TIMEOUT_CHAT,
    )


# ── 聊天降级 ────────────────────────────────────────


def fallback_chat_reply() -> str:
    """降级：从 llm_prompt.py 回复池随机选取"""
    return random.choice(FALLBACK_CHAT_REPLIES)


# ══════════════════════════════════════════════════════════
#  局间剧情模块（无状态：不写文件、不读写 session、不做缓存）
# ══════════════════════════════════════════════════════════


def generate_story(context: dict) -> list[dict] | None:
    """根据本局上下文生成一段多角色 ADV 剧情

    Args:
        context: {
            round, quadrant, passed, rating, heat, salt,
            cards: {卡型: 数量}, history: [方向, ...]
        }

    Returns:
        规范化后的对话行 [{speaker, speakerName, text}, ...]；
        调用失败、JSON 解析失败或内容不达标时返回 None（由前端降级到本地 A 版剧本）
    """
    quadrant = str(context.get("quadrant") or "wasteland")
    npc_id = STORY_NPC_BY_QUADRANT.get(quadrant, "")
    if npc_id and npc_id in STORY_SPEAKER_PROFILES:
        profile = STORY_SPEAKER_PROFILES[npc_id]
        npc_hint = (
            f"必须安排 {npc_id}（{profile['name']}）出场，并给 ta "
            f"{STORY_NPC_MIN_LINES}-{STORY_NPC_MAX_LINES} 句台词。"
            f"语气：{profile['voice']}"
        )
    else:
        # 荒原寂静，不出 NPC；少了一个说话人，要求两人各多说一句把总句数补够
        npc_hint = (
            "本段不安排 NPC 出场，只写看山与旅行者的二人戏；"
            f"因此看山与旅行者都要多用上骨架里的可选句，把总句数补到 {STORY_TARGET_MIN_LINES} 句以上"
        )

    user_prompt = STORY_USER_PROMPT_TEMPLATE.format(
        round=_to_int(context.get("round"), 1),
        quadrant_name=STORY_QUADRANT_NAMES.get(quadrant, "知识荒原"),
        flavor_hint=QUADRANT_FLAVOR_HINTS.get(quadrant, QUADRANT_FLAVOR_HINTS["wasteland"]),
        npc_hint=npc_hint,
        passed="结算通过" if context.get("passed", True) else "结算未通过",
        rating=str(context.get("rating") or "无"),
        heat=_to_float_text(context.get("heat")),
        salt=_to_float_text(context.get("salt")),
        card_summary=_format_card_summary(context.get("cards") or {}),
        round_imprint=_format_round_imprint(context),
        recent_history=_format_history(context.get("history") or []),
    )

    raw = call_tongyi(
        STORY_SYSTEM_PROMPT,
        user_prompt,
        model=TONGYI_MODEL_STORY,
        max_tokens=STORY_MAX_TOKENS,
        temperature=STORY_TEMPERATURE,
        timeout=TONGYI_TIMEOUT_STORY,
    )
    if not raw:
        return None

    return _normalize_story_lines(_parse_story_json(raw))


# ── 剧情上下文格式化 ────────────────────


def _to_int(value, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _to_float_text(value) -> str:
    try:
        return f"{float(value):.1f}"
    except (TypeError, ValueError):
        return "0.0"


def _format_card_summary(cards: dict) -> str:
    parts = [
        f"{card_type} {count} 张"
        for card_type, count in cards.items()
        if isinstance(count, int) and count > 0
    ]
    return "、".join(parts) if parts else "本局没有合成卡牌"


def _format_round_imprint(context: dict) -> str:
    """把数值上下文转成可写进台词的自然语言印记，避免 AI 直接复述数字。"""
    cards = context.get("cards") or {}
    dominant_cards = [
        str(card_type)
        for card_type, count in sorted(cards.items(), key=lambda item: item[1], reverse=True)
        if isinstance(count, int) and count > 0
    ][:2]

    try:
        heat = float(context.get("heat"))
        salt = float(context.get("salt"))
    except (TypeError, ValueError):
        heat = 0.0
        salt = 0.0

    if abs(heat) >= abs(salt) + 0.5:
        vector_hint = "这一步更像被热度推着走，话题感很强"
    elif abs(salt) >= abs(heat) + 0.5:
        vector_hint = "这一步更像被盐度牵引，辨析和挑刺感更强"
    elif abs(heat) > 0.1 or abs(salt) > 0.1:
        vector_hint = "这一步热度和盐度比较均衡，像是在边走边校准"
    else:
        vector_hint = "这一步方向还很轻，像刚在纸上落下一笔"

    passed_hint = "刚才的组合已经被知北针接住了" if context.get("passed", True) else "刚才的组合还有点摇晃"
    card_hint = f"玩家刚刚主要带上了{'、'.join(dominant_cards)}" if dominant_cards else "玩家刚刚没有留下特别突出的卡牌类型"
    history_hint = _format_history(context.get("history") or [])
    return f"{passed_hint}；{vector_hint}；{card_hint}；最近移动：{history_hint}"


def _format_history(history: list) -> str:
    labels = [
        STORY_DIRECTION_LABELS.get(str(direction), str(direction))
        for direction in list(history)[-3:]
        if direction
    ]
    return " → ".join(labels) if labels else "暂无移动记录"


# ── 剧情输出解析与规范化 ──────────────────


def _parse_story_json(raw: str) -> list[dict]:
    """宽容解析模型输出：剥离 ```json 围栏后截取首个 JSON 数组

    当模型因 max_tokens 截断导致 JSON 未闭合时，尝试从最后一个完整的 }
    处截断并补上 ] 进行恢复，避免整段丢弃。
    """
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    start = text.find("[")
    if start == -1:
        print(f"[ai_service] 剧情输出未找到 JSON 数组起始: {text[:80]}")
        return []

    end = text.rfind("]")
    if end > start:
        # 正常路径：JSON 完整闭合
        candidate = text[start:end + 1]
    else:
        # 截断恢复：找到最后一个完整的 } 并补上 ]
        last_brace = text.rfind("}")
        if last_brace <= start:
            print(f"[ai_service] 剧情输出无完整对象，无法恢复: {text[:80]}")
            return []
        candidate = text[start:last_brace + 1] + "]"
        print(f"[ai_service] 剧情 JSON 被截断，尝试从最后一个 }} 恢复（{len(candidate)} 字符）")

    try:
        parsed = json.loads(candidate)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"[ai_service] 剧情 JSON 解析失败: {e}")
        return []

    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]


def _normalize_story_lines(items: list[dict]) -> list[dict] | None:
    """过滤非法角色、覆盖显示名、截断超长台词；不达标时返回 None"""
    lines: list[dict] = []
    for item in items:
        speaker = str(item.get("speaker") or "").strip()
        profile = STORY_SPEAKER_PROFILES.get(speaker)
        if profile is None:
            continue
        text = _truncate_story_line(str(item.get("text") or "").strip(), speaker)
        if not text:
            continue
        lines.append({
            "speaker": speaker,
            "speakerName": profile["name"],
            "text": text,
        })

    lines = lines[:STORY_MAX_LINES]
    if len(lines) < STORY_MIN_LINES:
        print(f"[ai_service] 剧情句数不足（{len(lines)} < {STORY_MIN_LINES}），视为生成失败")
        return None
    if not any(line["speaker"] == "kanshan" for line in lines):
        print("[ai_service] 剧情缺少看山台词，视为生成失败")
        return None
    return lines


def _truncate_story_line(text: str, speaker: str) -> str:
    """玩家台词限 25 字、其余限 80 字，尽量在句末标点处收尾"""
    limit = STORY_PLAYER_MAX_CHARS if speaker == "player" else STORY_LINE_MAX_CHARS
    if len(text) <= limit:
        return text

    clipped = text[:limit]
    for separator in ("。", "！", "？", "；", "，"):
        index = clipped.rfind(separator)
        if index >= limit // 2:
            return clipped[:index + 1]
    return clipped


# ══════════════════════════════════════════════════════════
#  阅读提示深度分析模块（功能 A · AI 高级模式）
# ══════════════════════════════════════════════════════════


def generate_deep_reading_hint(title: str, content: str) -> str | None:
    """生成文章深度阅读建议（AI 高级模式）

    截取文章前 1500 字控制 token 成本，调用通义千问生成个性化阅读分析。

    Returns:
        AI 生成的分析文本，失败时返回 None（由调用方降级）
    """
    # 截断控制成本：深度分析只需文章主体，不需全文
    truncated = content[:1500]
    user_prompt = HINT_DEEP_USER_TEMPLATE.format(title=title, content=truncated)

    print(f"[ai_service] hint 深度分析开始：title={title[:20]}... content_len={len(truncated)}")

    result = call_tongyi(
        HINT_DEEP_SYSTEM_PROMPT,
        user_prompt,
        model=TONGYI_MODEL_HINT,
        max_tokens=HINT_MAX_TOKENS,
        temperature=HINT_TEMPERATURE,
        timeout=TONGYI_TIMEOUT_HINT,
    )

    if result:
        print(f"[ai_service] hint 深度分析成功：{len(result)} 字")
    else:
        print("[ai_service] hint 深度分析失败，返回 None")

    return result


def fallback_deep_reading_hint() -> str:
    """深度分析降级文案"""
    return FALLBACK_HINT_DEEP


# ══════════════════════════════════════════════════════════
#  合成建议深度分析模块（背包合成页灯泡按钮）
# ══════════════════════════════════════════════════════════


def generate_deep_composition_hint(
    message: str,
    items: list[dict],
    card_summary: str,
    slot_summary: str,
    vector: list[float],
) -> str | None:
    """基于前端规则引擎结果生成更自然的合成建议。

    规则引擎仍是事实来源；AI 只负责把建议讲得更贴近玩家当前局面。
    """
    suggestions = []
    for index, item in enumerate(items[:4], start=1):
        title = str(item.get("title") or "")
        reason = str(item.get("reason") or "")
        action = str(item.get("action") or "")
        suggestions.append(f"{index}. {title}：{reason}；建议操作：{action}")

    vector_x = vector[0] if len(vector) > 0 else 0
    vector_y = vector[1] if len(vector) > 1 else 0
    user_prompt = COMPOSITION_HINT_USER_TEMPLATE.format(
        message=message,
        card_summary=card_summary,
        slot_summary=slot_summary,
        vector_x=_to_float_text(vector_x),
        vector_y=_to_float_text(vector_y),
        suggestions="\n".join(suggestions) if suggestions else "暂无规则建议",
    )

    print(f"[ai_service] composition hint 深度分析开始：items={len(items)}")

    result = call_tongyi(
        COMPOSITION_HINT_SYSTEM_PROMPT,
        user_prompt,
        model=TONGYI_MODEL_HINT,
        max_tokens=220,
        temperature=0.7,
        timeout=TONGYI_TIMEOUT_HINT,
    )

    if result:
        print(f"[ai_service] composition hint 深度分析成功：{len(result)} 字")
    else:
        print("[ai_service] composition hint 深度分析失败，返回 None")

    return result


def fallback_deep_composition_hint() -> str:
    """合成建议深度分析降级文案"""
    return FALLBACK_COMPOSITION_HINT_DEEP
