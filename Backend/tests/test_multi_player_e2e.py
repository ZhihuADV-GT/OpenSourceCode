"""E 层：多玩家端到端集成测试（前端→后端完整循环）

模拟 20 个玩家同时完成真实的前后端交互循环：
  1. POST /api/workspace/vectors — 同步卡槽，拿到各自向量
  2. GET  /api/workspace/vectors — 轮询向量
  3. POST /api/cards/dynamic     — 划线生成动态卡
  4. POST /api/judge             — 划线判定（命中预设点）
  5. POST /api/workspace/vectors — 再次同步，验证向量未被他人覆盖

每个玩家带不同的 X-Player-Id 头，并发跑完后逐人核验：
  - 自己 POST 的向量 == 自己 GET 到的向量（不被他人覆盖）
  - 自己生成的动态卡 ID 唯一且归属正确
  - 自己的 judge 命中了正确的预设卡
  - 全链路零串扰

依赖：fastapi TestClient（httpx 同步封装），每线程独立 client。
"""

from __future__ import annotations

import concurrent.futures
import json
import threading
from pathlib import Path

import pytest

_BACKEND_DIR = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(_BACKEND_DIR))

from fastapi.testclient import TestClient
from game.api.api import app


# ── 辅助工具 ─────────────────────────────────────────────────────────────

_PLAYER_COUNT = 20
_ARTICLE_ID = "article_1"

# article_1 的 content 前 100 字符（用于动态划线，避开预设 linespot）
# content 开头："给大家科普一个常识：\n某个行业..."
# 预设 linespot 区间：[11,39], [40,62], [206,239], [321,411], [435,466], [572,610]
# 安全区间：[63, 120]（在 linespot 2 和 3 之间）
_DYNAMIC_TEXT_START = 63
_DYNAMIC_TEXT_END = 120


def _make_client() -> TestClient:
    """每线程独立 TestClient，共享 app 实例（共享 session/存储）"""
    return TestClient(app)


def _player_headers(player_id: str) -> dict[str, str]:
    return {"X-Player-Id": player_id}


# ── 单玩家完整循环 ────────────────────────────────────────────────────────

def _run_player_loop(player_index: int) -> dict:
    """单个玩家跑完完整的前后端循环，返回每步的结果供断言"""
    player_id = f"player_{player_index:02d}"
    result = {"player_id": player_id, "errors": []}

    client = _make_client()
    headers = _player_headers(player_id)

    # ── Step 1: POST /api/workspace/vectors ──
    # 所有玩家使用相同的 slot 配置（slot_1 + article_1_card_1）
    # 矩阵布局有效位置是 slot_1~slot_16，slot_0 不在布局内
    slots = [["slot_1", "article_1_card_1"]]

    try:
        resp = client.post(
            "/api/workspace/vectors",
            json={"slots": slots},
            headers=headers,
        )
        assert resp.status_code == 200, f"Step1 status={resp.status_code}"
        step1_data = resp.json()
        result["step1_vector"] = step1_data["instant_vector"]
    except Exception as e:
        result["errors"].append(f"Step1: {e}")
        return result

    # ── Step 2: GET /api/workspace/vectors（轮询）──
    try:
        resp = client.get(
            "/api/workspace/vectors",
            headers=headers,
        )
        assert resp.status_code == 200, f"Step2 status={resp.status_code}"
        step2_data = resp.json()
        result["step2_vector"] = step2_data["instant_vector"]
    except Exception as e:
        result["errors"].append(f"Step2: {e}")
        return result

    # ── Step 3: POST /api/cards/dynamic ──
    # 每个玩家划不同的文本区间（通过偏移 player_index），确保 hash 不同
    start = _DYNAMIC_TEXT_START + player_index
    end = _DYNAMIC_TEXT_END + player_index
    try:
        resp = client.post(
            "/api/cards/dynamic",
            json={
                "articleId": _ARTICLE_ID,
                "paragraphIndex": 0,
                "startOffset": start,
                "endOffset": end,
                "round": 1,
            },
            headers=headers,
        )
        assert resp.status_code == 200, f"Step3 status={resp.status_code}"
        step3_data = resp.json()
        result["step3_card_id"] = step3_data.get("card", {}).get("card_id")
        result["step3_hit"] = step3_data.get("hit")
    except Exception as e:
        result["errors"].append(f"Step3: {e}")
        return result

    # ── Step 4: POST /api/judge（命中预设 linespot）──
    # 使用 article_1_card_1 的预设区间 [11, 39]
    try:
        resp = client.post(
            "/api/judge",
            json={
                "articleId": _ARTICLE_ID,
                "paragraphIndex": 0,
                "startOffset": 11,
                "endOffset": 39,
            },
            headers=headers,
        )
        assert resp.status_code == 200, f"Step4 status={resp.status_code}"
        step4_data = resp.json()
        result["step4_hit"] = step4_data.get("hit")
        result["step4_card_id"] = step4_data.get("card", {}).get("card_id")
    except Exception as e:
        result["errors"].append(f"Step4: {e}")
        return result

    # ── Step 5: 再次 POST /api/workspace/vectors（验证向量未被覆盖）──
    try:
        resp = client.post(
            "/api/workspace/vectors",
            json={"slots": slots},
            headers=headers,
        )
        assert resp.status_code == 200
        step5_data = resp.json()
        result["step5_vector"] = step5_data["instant_vector"]
    except Exception as e:
        result["errors"].append(f"Step5: {e}")
        return result

    # ── Step 6: GET 轮询最终确认 ──
    try:
        resp = client.get(
            "/api/workspace/vectors",
            headers=headers,
        )
        assert resp.status_code == 200
        step6_data = resp.json()
        result["step6_vector"] = step6_data["instant_vector"]
    except Exception as e:
        result["errors"].append(f"Step6: {e}")
        return result

    return result


# ── 测试主体 ─────────────────────────────────────────────────────────────

class TestMultiPlayerEndToEnd:
    """20 玩家并发端到端集成测试"""

    def test_all_players_complete_full_loop(self):
        """所有 20 玩家并发跑完完整链路，零错误"""
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=_PLAYER_COUNT) as pool:
            futures = [
                pool.submit(_run_player_loop, i)
                for i in range(_PLAYER_COUNT)
            ]
            for f in concurrent.futures.as_completed(futures):
                results.append(f.result())

        # 所有玩家无错误
        errors = []
        for r in results:
            if r["errors"]:
                errors.append(f"{r['player_id']}: {r['errors']}")
        assert not errors, f"{len(errors)} 个玩家出错:\n" + "\n".join(errors[:5])

    def test_vectors_isolated_per_player(self):
        """每个玩家的向量不被其他玩家覆盖"""
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=_PLAYER_COUNT) as pool:
            futures = [
                pool.submit(_run_player_loop, i)
                for i in range(_PLAYER_COUNT)
            ]
            for f in concurrent.futures.as_completed(futures):
                results.append(f.result())

        for r in results:
            if r["errors"]:
                continue
            # Step1 POST 返回的向量 == Step2 GET 轮询到的向量
            assert r["step1_vector"] == r["step2_vector"], (
                f"{r['player_id']}: POST 向量 {r['step1_vector']} != "
                f"GET 轮询向量 {r['step2_vector']}"
            )
            # Step5 再次 POST == Step6 再次 GET（循环后半段也一致）
            assert r["step5_vector"] == r["step6_vector"], (
                f"{r['player_id']}: 第二次 POST 向量 {r['step5_vector']} != "
                f"第二次 GET 向量 {r['step6_vector']}"
            )
            # 前半段和后半段向量相同（同一张卡，同一套计算）
            assert r["step1_vector"] == r["step5_vector"], (
                f"{r['player_id']}: 第一次向量 {r['step1_vector']} != "
                f"第二次向量 {r['step5_vector']}（被他人覆盖？）"
            )

    def test_dynamic_cards_all_unique(self):
        """20 玩家生成的动态卡 ID 全部不同"""
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=_PLAYER_COUNT) as pool:
            futures = [
                pool.submit(_run_player_loop, i)
                for i in range(_PLAYER_COUNT)
            ]
            for f in concurrent.futures.as_completed(futures):
                results.append(f.result())

        card_ids = [
            r["step3_card_id"]
            for r in results
            if r.get("step3_card_id") and not r["errors"]
        ]
        assert len(card_ids) == len(set(card_ids)), (
            f"动态卡 ID 碰撞: {len(card_ids)} 个 ID 中有重复\n"
            f"ID 列表: {card_ids}"
        )

    def test_judge_hits_preset_for_all_players(self):
        """所有玩家的 judge 请求都命中预设卡"""
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=_PLAYER_COUNT) as pool:
            futures = [
                pool.submit(_run_player_loop, i)
                for i in range(_PLAYER_COUNT)
            ]
            for f in concurrent.futures.as_completed(futures):
                results.append(f.result())

        for r in results:
            if r["errors"]:
                continue
            assert r.get("step4_hit") is True, (
                f"{r['player_id']}: judge 未命中预设卡"
            )
            assert r.get("step4_card_id") == "article_1_card_1", (
                f"{r['player_id']}: 命中了错误的预设卡 "
                f"(期望 article_1_card_1, 实际 {r.get('step4_card_id')})"
            )

    def test_same_card_same_vector_across_players(self):
        """所有玩家用同一张卡（article_1_card_1）算出的向量完全一致"""
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=_PLAYER_COUNT) as pool:
            futures = [
                pool.submit(_run_player_loop, i)
                for i in range(_PLAYER_COUNT)
            ]
            for f in concurrent.futures.as_completed(futures):
                results.append(f.result())

        vectors = [
            tuple(r["step1_vector"])
            for r in results
            if not r["errors"]
        ]
        assert len(set(vectors)) == 1, (
            f"同一张卡算出了不同向量（计算被污染）:\n"
            f"去重后: {set(vectors)}"
        )


class TestMultiPlayerArticleGenerate:
    """多玩家并发文章生成端到端"""

    def test_concurrent_article_generate_isolation(self):
        """20 玩家并发调用 /api/articles/generate，各自拿到自己的文章"""
        results = {}
        lock = threading.Lock()

        def _generate(player_index: int):
            player_id = f"player_gen_{player_index:02d}"
            client = _make_client()
            headers = _player_headers(player_id)

            # 所有玩家使用相同的 slot 配置
            slots = [["slot_1", "article_1_card_1"]]

            resp = client.post(
                "/api/articles/generate",
                json={"slots": slots, "use_ai": False},  # 纯拼接模式，不调 AI
                headers=headers,
            )
            with lock:
                results[player_id] = {
                    "status": resp.status_code,
                    "body": resp.json(),
                }

        with concurrent.futures.ThreadPoolExecutor(max_workers=_PLAYER_COUNT) as pool:
            futures = [pool.submit(_generate, i) for i in range(_PLAYER_COUNT)]
            concurrent.futures.wait(futures)

        # 所有请求成功
        failures = [
            f"{pid}: status={r['status']}"
            for pid, r in results.items()
            if r["status"] != 200
        ]
        assert not failures, f"文章生成失败:\n" + "\n".join(failures[:5])

        # 每人都拿到了文章（响应结构完整）
        for pid, r in results.items():
            body = r["body"]
            assert "title" in body, f"{pid}: 响应缺 title"
            assert "content" in body, f"{pid}: 响应缺 content"
            # title 可为空（单卡配置不一定生成标题），但 content 必须有
            assert len(body["content"]) > 0, f"{pid}: content 为空"
