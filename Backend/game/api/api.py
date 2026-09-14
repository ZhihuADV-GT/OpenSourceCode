from __future__ import annotations

import hmac
import itertools
import os
import random
import threading
import time
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from game.api.ai_service import (
    generate_comment,
    generate_chat_reply,
    generate_story,
    generate_deep_reading_hint,
    generate_deep_composition_hint,
    fallback_comment,
    fallback_chat_reply,
    fallback_deep_composition_hint,
)
from game.api.article_generator import generate_article
from game.api.llm_prompt import SEARCH_KEYWORDS_POOL, STORY_QUADRANT_NAMES
from game.api.llm_config import TONGYI_MODEL_STORY
# 卡牌数值规则 + 卡型字面量的单一数据源
from game.numerics.card_rules import (
    classify_card,
    clamp_card_vector,
    display_card_type,
    normalize_card_type,
)
from game.numerics.matrix_vector_system import MatrixVectorSystem, Vector2D  # 新增
from game.api.dynamic_card_service import resolve_dynamic_selection
from game.api.dynamic_card_store import save_dynamic_card
from game.api.session import get_session
from game.api.zhihu_service import (
    OAUTH_STATE_COOKIE_NAME,
    OAUTH_STATE_COOKIE_PATH,
    OAUTH_STATE_TTL_SECONDS,
    SESSION_COOKIE_NAME,
    OAuthSessionStore,
    OneTimeOAuthStateStore,
    ZhihuApiClient,
    ZhihuConfig,
    ZhihuServiceError,
)
from game.article_store import discover_article_files, read_json_like
from game.data_loader import load_article
from game.models import Article as EngineArticle
from game.models import LineSpot, SaltCard

_session = get_session()
_zhihu_client = ZhihuApiClient()
_zhihu_state_store = OneTimeOAuthStateStore()
_zhihu_session_store = OAuthSessionStore()

# 动态卡 ID 单调计数器：保证同进程内绝对唯一，不依赖时钟分辨率
# Windows 上 time_ns() 分辨率仅 ~15.6ms，24 线程同毫秒会碰撞
_CARD_ID_COUNTER = itertools.count()

# 文章库的目录常量、发现逻辑与 JSON 读取统一在 game.article_store（叶子模块）。
# 这里曾经有一份 _discover_article_files 加 `ARTICLE_FILES = _discover_article_files()`
# 的模块级快照，且只在 /api/articles/random 的 AI 生成分支里用 `global ARTICLE_FILES`
# 刷新；matrix_vector_system 那份同名快照则从不刷新，两份分歧导致新生成文章的
# 预设卡静默加载失败。快照还要求「每个往 article_lib 写文件的地方都记得刷新」，
# 漏一处就复发，所以两边都改成查找时实时扫描。详见 article_store 模块 docstring
# 与 tests/test_article_file_cache.py。


def _auto_generate_ai_article() -> bool:
    """自动调用预处理管道生成新的AI文章
    
    从 llm_prompt.py 的 SEARCH_KEYWORDS_POOL 中随机选取关键词。
    直接调用 game.preprocess.zhihu_pipeline.run_pipeline，不再走 subprocess。
    
    Returns:
        bool: 是否成功生成AI文章
    """
    from game.preprocess.zhihu_pipeline import run_pipeline
    
    # 从关键词池随机选取一个关键词
    keyword = random.choice(SEARCH_KEYWORDS_POOL)
    print(f'[auto-generate] 开始调用预处理管道，关键词：{keyword}')
    
    try:
        return run_pipeline(keyword=keyword, count=3)
    except Exception as e:
        print(f'[auto-generate] 预处理管道调用异常：{e}')
        return False


class ArticleResponse(BaseModel):
    """游戏初始化文章响应 - 仅包含前端需要的非敏感数据
    
    根据通信协议v1.0，此接口必须剔除所有敏感信息：
    - linespots (盐选卡预设位置)
    - attribute_x/attribute_y (向量值)
    - informationPoints (卡片详细信息)
    """
    id: str
    title: str
    content: str  # 全文纯文本，换行符用 \\n 表示
    target_value: int | None = None  # 协议要求使用 snake_case


class JudgeRequest(BaseModel):
    """玩家划线判定请求 - 根据通信协议v1.0
    
    前端发送玩家划线的区间信息，后端进行命中判定
    """
    articleId: str        # 文章ID
    paragraphIndex: int   # 段落索引（当前实现中只支持单段落，通常为0）
    startOffset: int      # 划线起始字符偏移量（含）
    endOffset: int        # 划线结束字符偏移量（不含，遵循 JS Range）


class DynamicCardRequest(BaseModel):
    """动态划线判定请求（POST /api/cards/dynamic，新端点）

    前四个字段与 JudgeRequest 逐字一致，前端可以直接复用 buildSelectionPayload 的产物。
    多出的 round 是新端点专属：划线判定这条链路上没有「局」的概念（JudgeRequest 及其
    同族都不带 round；后端唯一带 round 的是 StoryRequest，那是局间剧情，与划线无关），
    而动态卡配额必须按局计——按 articleId 计的话，玩家一局内换 3 篇文章
    就能刷 18 张卡，把 20 格背包里的预设卡全挤出去（handleFindMoreNotes 允许一局
    读多篇文章且保留背包）。

    round 是可选的：前端没传就跳过配额检查，不因为缺字段把玩家挡在门外。
    """
    articleId: str
    paragraphIndex: int = 0
    startOffset: int
    endOffset: int
    round: int | None = None


app = FastAPI(title="Zhihu Article Game API")


def _cors_origins() -> list[str]:
    """返回显式配置的前端 origin；不允许 credential 请求使用通配符。"""
    raw_origins = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173")
    origins = [origin.strip().rstrip("/") for origin in raw_origins.split(",") if origin.strip()]
    return origins or ["http://localhost:5173"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _load_engine_articles() -> list[EngineArticle]:
    # 每次调用实时扫描 article_lib，不读模块级快照（理由见文件顶部注释）
    files = discover_article_files()
    if not files:
        raise RuntimeError("No article JSON files found in backend/article_lib.")
    return [load_article(path) for path in files]


def _article_to_response(article: EngineArticle) -> ArticleResponse:
    """将引擎文章对象转换为前端响应格式
    
    【关键安全处理】
    只返回前端需要的4个基础字段，完全剔除：
    - linespots (盐选卡预设划线点)
    - vector_x/vector_y (向量属性)
    - card_type/rarity (卡片类型信息)
    """
    return ArticleResponse(
        id=article.id,
        title=article.title,
        content=article.content,  # 直接使用原始内容，保留 \n 换行符
        target_value=article.target_value,
    )


def _get_raw_linespots(article: EngineArticle) -> list[dict]:
    """读取文章对应 JSON 文件中的原始 linespots 数据

    LineSpot 模型保留判定所需的标量字段；card_id 仍从原始 JSON 获取，
    用于对齐协议的 JudgeResult.card 格式。
    """
    for path in discover_article_files():
        payload = read_json_like(path)
        if str(payload.get("id")) == article.id:
            return payload.get("linespots", [])
    return []


# 卡型字面量统一走 game.numerics.card_rules：
# 内部规范形式不带「卡」（观点/情绪/漏洞/修辞），
# 协议出口（_spot_to_card_response，服务 /api/judge 与 /api/cards/dynamic）
# 用 display_card_type 加回后缀。
# 此处原有的 _normalize_card_type（加「卡」）与 card_rules.normalize_card_type（去「卡」）
# 方向相反，是卡型字面量分裂的源头之一，已删除。


def _find_best_spot(article: EngineArticle, start: int, end: int) -> tuple[int, LineSpot | None, int]:
    """查找最佳匹配的划线点

    start/end 是玩家选区的前端 convention：[start, end)，end 不包含。
    article.linespots 中的 canonical start/end 仍是闭区间 [start, end]。
    
    【协议规则 - 已优化】
    - 重叠率范围：25%-150%（原60%-100%，更尊重玩家选择）
    - 允许适度多划（不超过预设区间的3倍，原为2倍）
    - 重叠率 = (重叠长度 / 预设区间长度) * 100%
    """
    selected_start, selected_end_exclusive = sorted((start, end))
    if selected_end_exclusive <= selected_start:
        return -1, None, 0

    selected_end = selected_end_exclusive - 1
    selected_len = selected_end_exclusive - selected_start
    
    best_index = -1
    best_spot: LineSpot | None = None
    best_rate = 0

    for index, spot in enumerate(article.linespots):
        target_len = spot.end - spot.start + 1
        
        overlap_start = max(selected_start, spot.start)
        overlap_end = min(selected_end, spot.end)
        overlap = max(0, overlap_end - overlap_start + 1)
        
        rate = int((overlap / target_len) * 100)

        # 【优化】放宽多划限制：从2倍提升到3倍
        if selected_len > target_len * 3:
            rate = 0  # 多划太严重，判定为无效

        # 【优化】允许适度超出：上限从100%提升到150%
        if rate > 150:
            rate = 0  # 直接设为0，表示无效划线

        if rate > best_rate:
            best_rate = rate
            best_spot = spot
            best_index = index

    return best_index, best_spot, best_rate


def _spot_to_card_response(article: EngineArticle, spot: LineSpot, index: int) -> dict:
    """将命中的划线点转换为协议 JudgeResult.card 格式

    【协议要求】
    - 优先使用文章 JSON 中原始的 card_id
    - attribute_value: 使用文章 JSON 中该 linespot 的理解点贡献值
    - card_type: 统一为 观点卡/情绪卡/漏洞卡/修辞卡 格式
    - start/end: 命中 linespot 的 canonical range；后端内部 convention 为闭区间 [start, end]
    - 不返回 attribute_x/attribute_y (前端不需要知道)

    注意：start/end 来自后端命中的真实 LineSpot，而不是玩家请求中的
    startOffset/endOffset。前端 Adapter 会把闭区间转换成 [start, end) 使用。
    """
    raw_cards = _get_raw_linespots(article)
    card_id = raw_cards[index].get("card_id", f"{article.id}_card_{index + 1}")
    return {
        "card_id": card_id,
        "attribute_value": int(spot.attribute_value),
        "card_type": display_card_type(spot.card_type),
        "start": spot.start,
        "end": spot.end,
    }


def _classify_card_type(text: str) -> tuple[str, int, float, float]:
    """本地关键词判型的薄封装：拆成 (card_type, attribute_value, vector_x, vector_y)

    判定本体（关键词池 + 优先级瀑布 + 量纲）唯一地定义在
    game.numerics.card_rules.classify_card。本函数只做「拆成 4 元组」这一层适配：
    dynamic_card_service.resolve_dynamic_selection 的 classify 形参、
    tests/test_dynamic_card_store.py 与 tests/test_dynamic_card_live.py 都按
    4 元组契约调它，改签名会连带改调用方与测试，不值得。

    card_type 用内部规范形式（观点/情绪/漏洞/修辞，不带「卡」），
    进协议响应体前由调用方用 display_card_type 转成展示形式。

    这里原本是一整份实现，与 hint_service._classify_card_type_simple 的关键词池
    及优先级瀑布逐字重复，只差返回值（那边只要卡型）。两份共存时任何一侧
    改了阈值，就会出现「看山提示这里藏着情绪卡，玩家划出来却是观点卡」。
    关键词池高频单字导致的无区分度问题是已知缺陷，本轮只合并不改判定，
    详见 card_rules 里「本地关键词分类器」节的说明。
    """
    result = classify_card(text)
    return (result.card_type, result.attribute_value, result.vector_x, result.vector_y)


def _generate_dynamic_card(
    article_id: str,
    text: str,
    start_offset: int,
    end_offset: int,
    *,
    card_type_override: str = "",
    vector_override: tuple[float, float] | None = None,
) -> dict:
    """
    为玩家选区动态生成临时卡牌
    
    Args:
        article_id: 文章ID
        text: 玩家选中的文本
        start_offset: 起始字符偏移（含）
        end_offset: 结束字符偏移（不含）
        card_type_override: 覆盖本地分类器的判型（规范形式，不带「卡」）。
            /api/cards/dynamic 用 AI 的判型走这里：AI 能看上下文，判型比关键词池准
            （本地分类器实测 13 种划法里 12 种输出完全相同）。不传则行为与以前一致。
        vector_override: 覆盖本地分类器的向量。量纲跟着型别走（修辞是乘数、
            其余是整数向量），AI 改判型别时必须整个换掉。数值由 card_rules 单一
            数据源派生，绝不采信 AI 输出的数值（见 dynamic_card_service 红线②）。
    
    Returns:
        符合协议的 card 字典
    """
    import hashlib
    import time
    
    # 分类并计算属性（先分类，再生成ID）
    card_type, attribute_value, vector_x, vector_y = _classify_card_type(text)
    if card_type_override:
        card_type = normalize_card_type(card_type_override)
    if vector_override is not None:
        vector_x, vector_y = vector_override
    # 兜底钳制：分类器的硬编码向量必须始终符合 Backend/article生成规则.md，
    # 走同一份规则可防止以后调数值时再次漂移到区间外
    vector_x, vector_y = clamp_card_vector(card_type, vector_x, vector_y)
    
    # 【优化】生成唯一卡牌ID（包含类型信息，便于跨局重建）
    # 格式: {article_id}_dynamic_{type}_{hash}_{timestamp_ns}_{counter}
    # 例如: ai_52a4dadd_dynamic_观点_68e816e1_1726123456789012345_42
    # time_ns() 提供时间信息（便于调试），counter 保证绝对唯一（不依赖时钟分辨率）
    text_hash = hashlib.md5(text.encode('utf-8')).hexdigest()[:8]
    timestamp_ns = time.time_ns()  # 纳秒时间戳，19位整数
    counter = next(_CARD_ID_COUNTER)  # 进程内单调递增，保证绝对唯一
    
    # ID 里的 type 用内部规范形式（不带「卡」）：跨局重建时
    # _reconstruct_dynamic_card 直接拿它查降级向量表，带后缀会查不到而静默退回默认值
    type_short = normalize_card_type(card_type)
    card_id = f"{article_id}_dynamic_{type_short}_{text_hash}_{timestamp_ns}_{counter}"
    
    # 构建响应（协议出口：card_type 用带「卡」的展示形式，与预设点分支一致）
    return {
        "card_id": card_id,
        "attribute_value": attribute_value,
        "card_type": display_card_type(card_type),
        "start": start_offset,
        "end": end_offset - 1,  # 转换为闭区间 [start, end]
        "attribute_x": vector_x,  # 【修复】添加向量x分量
        "attribute_y": vector_y,  # 【修复】添加向量y分量
    }


def _persist_dynamic_card(
    article_id: str,
    card_dict: dict,
    text: str,
    *,
    round_no: int | None = None,
    player_id: str = "default",
) -> bool:
    """把动态卡写入 session 缓存 + 落盘，返回落盘是否成功

    两步都必须做，缺一不可：
    - session 缓存：本局的向量计算（_load_card_by_id 第一级）要靠它拿到 text 与真实向量
    - 落盘：session 是纯内存全局单例，重启即失。不落盘的话 _reconstruct_dynamic_card
      只能给降级向量、text 恒为空，局末文章生成会整段丢掉这张卡。

    只写 dynamic_cards.json（不匹配 article_*/ai_* 两个 glob），避免动态卡混进
    预设 linespot 池而污染 _find_best_spot。

    /api/judge 与 /api/cards/dynamic 共用本函数：持久化逻辑曾经在这两处各写一份，
    任何一处漏改都会让另一条链路静默丢卡。
    """
    dynamic_card_obj = SaltCard(
        id=card_dict["card_id"],
        articleId=article_id,
        informationPointId="",  # 动态卡牌无预设ID
        text=text,              # 保存实际文本，文章生成链路靠它取原文
        # 响应体里是协议展示形式（带「卡」），入库前归一化为规范形式
        type=normalize_card_type(card_dict["card_type"]),
        rarity="动态发现",      # 标记为动态生成
        attribute_x=card_dict.get("attribute_x", 0.0),
        attribute_y=card_dict.get("attribute_y", 0.0),
        vector_array=[],
        title=f"{card_dict['card_type']}-{text[:10]}...",
    )
    _session.cache_card(dynamic_card_obj, player_id=player_id)
    saved = save_dynamic_card(
        card_dict,
        text,
        title=dynamic_card_obj.title,
        round_no=round_no,
    )
    print(f'[dynamic-card] 已缓存: {card_dict["card_id"]}, 落盘={saved}')
    return saved


# AI文章库上限：超过此数量后不再自动生成新文章
_MAX_AI_ARTICLES = 100

# AI 文章生成锁：防止多玩家同时触发 check-then-act 导致双倍 subprocess
_AI_GEN_LOCK = threading.Lock()


@app.get("/api/articles/random")
def get_random_article(category: str | None = None, exclude: str | None = None) -> ArticleResponse:
    """随机获取一篇文章
    
    Args:
        category: 文章类型 - "ai"表示只从AI文章中选择，None或空表示从所有文章中选择
        exclude: 逗号分隔的已读文章ID列表，返回结果会排除这些文章
    
    Returns:
        随机的一篇文章（不与 exclude 列表重复）
    
    Fallback策略（category="ai"时）：
    1. 从未读的AI文章中随机选择
    2. 如果全部AI文章都已读 且 AI文章总数 < 100 → 调用预处理管道生成新文章
    3. 如果AI文章已达100篇上限 或 生成失败 → 降级返回本地手动文章（article_*.json）
    4. 如果连本地文章也全部读完 → 返回默认示例文章
    """
    # 解析 exclude 参数
    exclude_ids = set()
    if exclude:
        exclude_ids = {eid.strip() for eid in exclude.split(',') if eid.strip()}
    
    articles = _load_engine_articles()
    
    # 如果请求AI文章
    if category == "ai":
        all_ai = [a for a in articles if a.id.startswith("ai_")]
        unread_ai = [a for a in all_ai if a.id not in exclude_ids]
        
        # 优先从未读的AI文章中选择
        if unread_ai:
            print(f'[random] 从 {len(unread_ai)} 篇未读AI文章中选择（共{len(all_ai)}篇，已读{len(exclude_ids)}篇）')
            selected = random.choice(unread_ai)
            return _article_to_response(selected)
        
        # 所有AI文章都已读，尝试生成新的（上限100篇）
        # 加锁防止多玩家同时触发 check-then-act 导致双倍生成
        with _AI_GEN_LOCK:
            if len(all_ai) < _MAX_AI_ARTICLES:
                print(f'[random] AI文章已全部读完（{len(all_ai)}/{_MAX_AI_ARTICLES}），尝试生成新文章...')
                success = _auto_generate_ai_article()
                
                if success:
                    # 无需再刷新快照：_load_engine_articles 每次实时扫描 article_lib
                    articles = _load_engine_articles()
                    new_ai = [a for a in articles if a.id.startswith("ai_") and a.id not in exclude_ids]
                    
                    if new_ai:
                        print(f'[random] AI生成成功！返回新文章: {new_ai[0].id}')
                        return _article_to_response(random.choice(new_ai))
                
                print('[random] AI生成失败，降级到本地手动文章')
            else:
                print(f'[random] AI文章已达上限（{len(all_ai)}/{_MAX_AI_ARTICLES}），降级到本地手动文章')
        
        # 降级：从本地手动文章（article_*.json）中选择未读的
        local_articles = [a for a in articles if a.id.startswith("article_") and a.id not in exclude_ids]
        if local_articles:
            print(f'[random] 降级：从 {len(local_articles)} 篇未读本地文章中选择')
            return _article_to_response(random.choice(local_articles))
        
        # 本地文章也全部读完，返回任意一篇本地文章
        local_all = [a for a in articles if a.id.startswith("article_")]
        if local_all:
            selected = random.choice(local_all)
            print(f'[random] 本地文章也已全部读完，返回随机本地文章: {selected.id}')
            return _article_to_response(selected)
        
        # 完全没有任何文章
        print('[random] 没有任何文章，返回默认示例')
        return ArticleResponse(
            id="default_fallback",
            title="默认示例文章（无可用数据）",
            content="这是游戏的默认示例文章。\n当后端没有加载任何真实文章时，系统会自动返回此备用内容。",
            target_value=50,
        )
    
    # 非AI类别：从所有文章中随机选择（排除已读）
    filtered = [a for a in articles if a.id not in exclude_ids]
    if filtered:
        selected = random.choice(filtered)
        print(f'[random] 随机选择文章：{selected.id}（排除 {len(exclude_ids)} 篇已读）')
        return _article_to_response(selected)
    
    if articles:
        selected = random.choice(articles)
        print(f'[random] 排除后无可用文章，返回随机：{selected.id}')
        return _article_to_response(selected)
    
    print('[random] 没有任何文章，返回默认示例')
    return ArticleResponse(
        id="default_fallback",
        title="默认示例文章（无可用数据）",
        content="这是游戏的默认示例文章。\n当后端没有加载任何真实文章时，系统会自动返回此备用内容。",
        target_value=50,
    )


# ── 每局文章生成接口 ────────────────────────────────────────


class ArticleGenerateRequest(BaseModel):
    """每局文章生成请求（协议链路7）

    前端在创作台合成完成后，携带卡槽快照请求后端生成文章。
    """
    slots: list[list[str]]          # 卡槽快照 [[slotId, cardId], ...]
    use_ai: bool = True             # 是否调用 AI 逐段生成；false 则纯卡牌拼接兜底


class BlueprintItem(BaseModel):
    """段落蓝图中的单条记录

    字段集由 游戏重点相关/收发数据json格式约定协议v4.0.md 明文规定（含
    weave_count），不得增删；契约测试见 tests/test_response_contract.py。
    """
    index: int
    role: str
    card_id: str
    card_type: str
    content_type: str
    template_id: str
    weave_count: int


class ArticleGenerateResponse(BaseModel):
    """每局文章生成响应

    【paragraphs / structure / lean / blueprint 目前前端一处都不读】
    RoundArticleWindow.vue 只取 title（L145）与 content（L123-124 逐字打字机），
    这四个字段是纯只写。仍然保留，删之前请先读完下面三条理由：

    1. 它们是 v4.0 协议的明文字段。收发数据json格式约定协议v4.0.md 给了完整
       JSON 样例（含 blueprint 的 7 个子字段），全流程前后端通信v4.0.md
       步骤 24 写的是「按 paragraphs 分段渲染」——设计意图是分段渲染，
       只是当前实现选了逐字打字机。属于「尚未落地」而不是「已废弃」，
       删字段等于单方面撕掉协议里预留的渲染入口。
    2. blueprint 是这条链路唯一的可观测面。AI 逐段生成跑偏时，只能靠
       role / template_id / weave_count 定位是哪一段、用了哪个模板、织入几张卡；
       与 /api/cards/dynamic 的 source、StoryResponse 的 debug 同一套思路。
    3. BlueprintItem(**item) 本身是一道校验：article_generator 少给一个键
       会在构造时直接抛 ValidationError（端点 500），而不是把残缺数据
       静默发给前端。

    代价是每次响应多序列化几 KB，以及端点里那条段数一致性警告。可接受。
    """
    title: str
    content: str
    paragraphs: list[str]
    structure: str
    lean: str
    blueprint: list[BlueprintItem]


@app.post("/api/articles/generate", response_model=ArticleGenerateResponse)
def generate_round_article(request: ArticleGenerateRequest) -> ArticleGenerateResponse:
    """
    每局文章生成接口（协议链路7）

    接收前端卡槽快照，调用 article_generator 生成结构化文章。
    流程：export_snapshot → build_blueprint → 逐段 AI 生成 → assemble
    """
    print(f'[article-generate] 收到生成请求，卡槽数: {len(request.slots)}, use_ai: {request.use_ai}')

    if not request.slots:
        raise HTTPException(status_code=400, detail="卡槽快照不能为空")

    # 1. 导出快照（矩阵 + 结构 + 向量 + 卡牌数据）
    matrix_system = MatrixVectorSystem()
    snapshot = matrix_system.export_snapshot(request.slots, auto_load_cards=True)

    print(f'[article-generate] 结构: {snapshot["structure_name"]}, '
          f'向量: ({snapshot["vector"].x:.4f}, {snapshot["vector"].y:.4f}), '
          f'卡牌数: {len(snapshot["cards_data"])}')

    # 2. 调用文章生成器
    try:
        result = generate_article(snapshot, title="", use_ai=request.use_ai)
    except Exception as e:
        print(f'[article-generate] 生成失败: {e}')
        raise HTTPException(status_code=500, detail=f"文章生成失败: {str(e)}")

    print(f'[article-generate] 生成完成: 结构={result["structure"]}, '
          f'段落数={len(result["paragraphs"])}, 基调={result["lean"]}')

    # paragraphs 已在 generate_article 里跟 blueprint 同步剔除空段，
    # 此处的段数即有效段数；但两者与 blueprint 对不上就说明过滤逻辑被破坏了
    if len(result["paragraphs"]) != len(result["blueprint"]):
        print(f'[article-generate] 警告：段落数({len(result["paragraphs"])}) '
              f'与蓝图数({len(result["blueprint"])}) 不一致')
    if not (result["content"] or "").strip():
        print('[article-generate] 警告：生成的文章内容为空，前端将展示错误提示')

    # 3. 构建响应
    blueprint_items = [
        BlueprintItem(**item) for item in result["blueprint"]
    ]

    return ArticleGenerateResponse(
        title=result["title"],
        content=result["content"],
        paragraphs=result["paragraphs"],
        structure=result["structure"],
        lean=result["lean"],
        blueprint=blueprint_items,
    )


@app.post("/api/judge")
def judge(
    request: JudgeRequest,
    x_player_id: str = Header(default="default", alias="X-Player-Id"),
) -> dict:
    """玩家划线判定接口
    
    接收前端发送的划线区间，优先与预设的 linespots 进行重叠率比对
    阈值：25% <= matchRate <= 150% 判定为命中预设点
    
    【新增兜底机制】
    如果未命中任何预设点，但玩家划线内容有效（5-200字），
    则动态生成临时卡牌，尊重玩家的自由选择。
    """
    articles = {article.id: article for article in _load_engine_articles()}
    article = articles.get(request.articleId)

    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")

    best_index, best_spot, best_rate = _find_best_spot(article, request.startOffset, request.endOffset)

    # 情况1：命中预设点（重叠率 >= 25%）
    if best_spot is not None and best_rate >= 25:
        return {
            "hit": True,
            "matchRate": best_rate,
            "card": _spot_to_card_response(article, best_spot, best_index),
        }

    # 情况2：未命中预设点，尝试动态生成卡牌
    selected_text = article.content[request.startOffset:request.endOffset].strip()
    
    # 有效性检查：文本长度在合理范围内
    if len(selected_text) < 5 or len(selected_text) > 200:
        return {
            "hit": False,
            "matchRate": best_rate,
            "message": "选区过短或过长，请重新划线",
        }
    
    # 动态生成临时卡牌
    dynamic_card_dict = _generate_dynamic_card(
        article_id=article.id,
        text=selected_text,
        start_offset=request.startOffset,
        end_offset=request.endOffset,
    )
    
    # 【关键】session 缓存 + 落盘：后续的向量计算与局末文章生成都要靠它拿到原文。
    # 与 /api/cards/dynamic 共用 _persist_dynamic_card，两边持久化行为保证一致。
    _persist_dynamic_card(article.id, dynamic_card_dict, selected_text, player_id=x_player_id)
    
    return {
        "hit": True,
        "matchRate": 0,  # 动态生成，无匹配率
        "card": dynamic_card_dict,
    }


@app.post("/api/cards/dynamic")
def create_dynamic_card(
    request: DynamicCardRequest,
    x_player_id: str = Header(default="default", alias="X-Player-Id"),
) -> dict:
    """AI 辅助的动态划线判定——划线的**主路径**（/api/judge 协议零改动）

    前端 ArticlePanel 对**所有**划线都先调本端点，/api/judge 降为异常兜底（后端未起 /
    网络断 / 超时）。顺序不能反过来：judge 的 miss 分支自己就会建一张本地分类器卡
    并落盘，先 judge 再调本端点会让同一次划线产生两张卡（两边文本不同 → L2 去重的
    hash 不命中），judge 建的那张孤儿卡还会让玩家下次划同一句时被误判「已经收集」。

    因此下面第一步的 linespot 比对不是可选的幂等保护，而是**必需**的：本端点接管了
    judge 的全部职责，不比一次就会把预设卡退化成动态卡。两边预设分支逐字等价
    （同 _find_best_spot、同 25% 阈值、同 _spot_to_card_response，只多一个 source），
    由 test_preset_branch_is_equivalent_to_judge 钉住。

    与 judge 的 miss 分支相比，本端点多三道闸：L2 同文去重、L3 每局 10 张配额、
    句边界扩展。judge 那边三者都没有，玩家可以无限刷卡把 20 格背包里的预设卡挤出去。

    响应体刻意与 JudgeResultDto 同构（hit/matchRate/card 或 hit/matchRate/message），
    前端可以直接复用 adaptJudgeResult / adaptSaltCard，包括那个
    canonicalEndOffset = dto.end + 1 的闭区间转换。额外多一个 source 字段
    （'ai' | 'local' | 'preset'）标记这次判定主要靠谁，前端不展示，只用于排查。

    耗时：AI 路径后端预算 15s（TONGYI_TIMEOUT_DYNAMIC_CARD），而前端全局 axios
    超时只有 5s——前端必须给这个请求单独覆盖超时，否则后端建卡成功但前端报超时，
    玩家重划会产生重复卡。

    降级：L1-L6 六级阶梯见 dynamic_card_service 模块 docstring。AI 挂了就退回
    本地判型 + 本地句边界扩展，结果仍严格优于引入 AI 之前的现状。
    """
    articles = {article.id: article for article in _load_engine_articles()}
    article = articles.get(request.articleId)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")

    # 幂等保护：这段选区其实命中了预设点，就直接给预设卡
    best_index, best_spot, best_rate = _find_best_spot(
        article, request.startOffset, request.endOffset,
    )
    if best_spot is not None and best_rate >= 25:
        print(f'[cards/dynamic] 选区实际命中预设点（{best_rate}%），直接返回预设卡')
        return {
            "hit": True,
            "matchRate": best_rate,
            "card": _spot_to_card_response(article, best_spot, best_index),
            "source": "preset",
        }

    outcome = resolve_dynamic_selection(
        article_id=article.id,
        content=article.content,
        start=request.startOffset,
        end=request.endOffset,
        round_no=request.round,
        classify=_classify_card_type,
    )
    if not outcome.hit:
        return outcome.response

    resolved = outcome.resolved or {}
    dynamic_card_dict = _generate_dynamic_card(
        article_id=article.id,
        text=outcome.text,
        start_offset=resolved["start"],
        end_offset=resolved["end"],
        card_type_override=resolved["type"],
        vector_override=(resolved["x"], resolved["y"]),
    )

    # round 跟着落盘：配额按局分区计数，后端重启也不会把配额重置
    _persist_dynamic_card(
        article.id, dynamic_card_dict, outcome.text,
        round_no=request.round, player_id=x_player_id,
    )
    print(f'[cards/dynamic] {resolved.get("path")} 建卡: {dynamic_card_dict["card_id"]}, '
          f'source={outcome.response.get("source")}, round={request.round}')

    return {**outcome.response, "card": dynamic_card_dict}


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


_SENSITIVE_ZHIHU_RESPONSE_KEYS = {
    "access_token",
    "refresh_token",
    "access_secret",
    "app_key",
    "authorization",
    "x-oauth-token",
}


def _sanitize_zhihu_public_data(value):
    """防止联调端点意外回显凭证字段；正文字符串不做内容重写。"""
    if isinstance(value, dict):
        return {
            key: _sanitize_zhihu_public_data(child)
            for key, child in value.items()
            if str(key).lower() not in _SENSITIVE_ZHIHU_RESPONSE_KEYS
        }
    if isinstance(value, list):
        return [_sanitize_zhihu_public_data(item) for item in value]
    return value


def _zhihu_config_error(missing: list[str]) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "code": "ZHIHU_NOT_CONFIGURED",
            "message": "知乎 OAuth/开放平台配置不完整，请检查后端 Secret Store。",
            "missing": missing,
        },
    )


def _clear_zhihu_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")


def _clear_zhihu_oauth_state_cookie(response: Response) -> None:
    response.delete_cookie(OAUTH_STATE_COOKIE_NAME, path=OAUTH_STATE_COOKIE_PATH)


def _zhihu_oauth_error(
    status_code: int,
    code: str,
    message: str,
) -> JSONResponse:
    """返回 callback 错误并立即清理浏览器 pre-auth state cookie。"""
    response = JSONResponse(
        status_code=status_code,
        content={"detail": {"code": code, "message": message}},
    )
    _clear_zhihu_oauth_state_cookie(response)
    return response


@app.get("/api/auth/zhihu/login")
def zhihu_login() -> RedirectResponse:
    """发起知乎黑客松 Authorization Code OAuth。"""
    config = ZhihuConfig.from_env()
    missing = config.missing_oauth_fields()
    if missing:
        raise _zhihu_config_error(missing)

    state = _zhihu_state_store.issue()
    response = RedirectResponse(
        url=_zhihu_client.authorization_url(config, state),
        status_code=302,
    )
    # state 同时保存在服务端和当前浏览器的短期 HttpOnly cookie 中，
    # 防止攻击者把自己的 OAuth callback 投递给另一位用户。
    response.set_cookie(
        key=OAUTH_STATE_COOKIE_NAME,
        value=state,
        httponly=True,
        secure=config.cookie_secure,
        samesite="lax",
        path=OAUTH_STATE_COOKIE_PATH,
        max_age=OAUTH_STATE_TTL_SECONDS,
    )
    return response


@app.get("/api/auth/zhihu/callback")
def zhihu_callback(request: Request) -> Response:
    """接收 authorization_code，并在后端完成 Token 交换。"""
    config = ZhihuConfig.from_env()
    missing = config.missing_oauth_fields()
    if missing:
        error = _zhihu_config_error(missing)
        return _zhihu_oauth_error(error.status_code, "ZHIHU_NOT_CONFIGURED", error.detail["message"])

    # 黑客松当前实测主参数是 authorization_code；兼容文档允许的 code。
    authorization_code = (
        request.query_params.get("authorization_code")
        or request.query_params.get("code")
    )
    if not authorization_code:
        return _zhihu_oauth_error(
            400,
            "OAUTH_CODE_MISSING",
            "知乎 OAuth 回调缺少 authorization_code；错误回调参数：NOT DOCUMENTED。",
        )

    # Skill 记录回调可能不返回 state；安全实现不绕过 CSRF 校验。
    callback_state = request.query_params.get("state")
    if not callback_state:
        return _zhihu_oauth_error(
            400,
            "OAUTH_STATE_MISSING",
            "知乎 OAuth 回调未返回 state，当前官方资料为 NOT DOCUMENTED，无法安全完成登录。",
        )

    browser_state = request.cookies.get(OAUTH_STATE_COOKIE_NAME)
    if not browser_state:
        return _zhihu_oauth_error(
            400,
            "OAUTH_BROWSER_STATE_MISSING",
            "知乎 OAuth 回调缺少当前浏览器的 pre-auth state，请重新发起登录。",
        )
    if not hmac.compare_digest(callback_state, browser_state):
        return _zhihu_oauth_error(
            400,
            "OAUTH_STATE_MISMATCH",
            "知乎 OAuth state 与当前浏览器不匹配，请重新发起登录。",
        )
    if not _zhihu_state_store.consume(callback_state):
        return _zhihu_oauth_error(
            400,
            "OAUTH_STATE_INVALID",
            "知乎 OAuth state 无效或已过期，请重新发起登录。",
        )

    try:
        token = _zhihu_client.exchange_code(config, authorization_code)
        user = _zhihu_client.get_user_profile(token.access_token)
    except ZhihuServiceError as exc:
        return _zhihu_oauth_error(exc.status_code, exc.code, exc.public_message)

    session_id, _ = _zhihu_session_store.create(token, user)
    response = RedirectResponse(url="/?zhihu_auth=success", status_code=303)
    _clear_zhihu_oauth_state_cookie(response)
    # Cookie 只保存随机 session id；OAuth token 留在服务端内存。
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        httponly=True,
        secure=config.cookie_secure,
        samesite="lax",
        path="/",
        max_age=token.expires_in,
    )
    return response


@app.get("/api/auth/zhihu/status")
def zhihu_auth_status(request: Request, response: Response) -> dict:
    """返回公开登录状态，不返回 App Key、Access Secret 或 OAuth token。"""
    config = ZhihuConfig.from_env()
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    session = _zhihu_session_store.get(session_id)
    if session_id and session is None:
        _clear_zhihu_cookie(response)
    return {
        "authenticated": session is not None,
        "configured": not bool(config.missing_oauth_fields()),
        "userApiConfigured": not bool(config.missing_user_api_fields()),
        "user": session.user.to_public_dict() if session is not None else None,
    }


@app.post("/api/auth/zhihu/logout")
def zhihu_logout(request: Request, response: Response) -> dict:
    """清理本项目服务端会话；远端 revoke/解绑在 Skill 中 NOT DOCUMENTED。"""
    _zhihu_session_store.delete(request.cookies.get(SESSION_COOKIE_NAME))
    _clear_zhihu_cookie(response)
    return {"authenticated": False}


@app.get("/api/auth/zhihu/profile")
def zhihu_user_profile(request: Request, response: Response) -> dict:
    """返回当前登录用户的公开资料（昵称/头像/uid），不暴露 OAuth token。"""
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    session = _zhihu_session_store.get(session_id)
    if session is None:
        _clear_zhihu_cookie(response)
        raise HTTPException(
            status_code=401,
            detail={
                "code": "ZHIHU_LOGIN_REQUIRED",
                "message": "请先使用知乎账号登录。",
            },
        )

    # 用 session 里的 access_token 调知乎 /user 接口
    import json as _json
    from urllib.request import Request as _Request, urlopen as _urlopen

    req = _Request(
        "https://openapi.zhihu.com/user",
        headers={"Authorization": f"Bearer {session.access_token}"},
    )
    try:
        with _urlopen(req, timeout=10) as resp:
            raw = _json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "ZHIHU_USER_API_ERROR",
                "message": "获取用户资料失败，请稍后重试。",
            },
        ) from exc

    # uid 是 int64，转字符串避免 JS 精度丢失
    return {
        "uid": str(raw.get("uid", "")),
        "fullname": raw.get("fullname", ""),
        "avatar_path": raw.get("avatar_path", ""),
    }


@app.get("/api/zhihu/test")
def zhihu_test(request: Request, response: Response) -> dict:
    """最小 OAuth 用户 API 验证端点：读取授权用户最近 1 条创作摘要。"""
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    session = _zhihu_session_store.get(session_id)
    if session is None:
        _clear_zhihu_cookie(response)
        raise HTTPException(
            status_code=401,
            detail={
                "code": "ZHIHU_LOGIN_REQUIRED",
                "message": "请先使用知乎账号登录，再请求知乎用户功能。",
            },
        )

    config = ZhihuConfig.from_env()
    missing = config.missing_user_api_fields()
    if missing:
        raise _zhihu_config_error(missing)

    try:
        data = _zhihu_client.get_user_contents(
            config,
            session.access_token,
            limit=1,
        )
    except ZhihuServiceError as exc:
        if exc.status_code in {401, 403}:
            _zhihu_session_store.delete(session_id)
            _clear_zhihu_cookie(response)
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "ZHIHU_OAUTH_SESSION_INVALID",
                    "message": "知乎授权已失效，请重新登录。",
                },
            ) from exc
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.public_message},
        ) from exc

    return {"ok": True, "api": "user_contents", "data": _sanitize_zhihu_public_data(data)}


# ── 阶段3配卡运算测试接口 ────────────────────────────────────────


class SlotSnapshot(BaseModel):
    """卡槽快照 - 根据通信协议v1.0
    
    前端发送完整卡槽快照，后端进行向量运算
    """
    slots: list[list[str]]  # [[slotId_1, cardId_A], [slotId_2, cardId_B], ...]


class VectorResult(BaseModel):
    """即时向量响应 - 根据通信协议v1.0
    
    返回二维向量 [x, y]，用于前端绘制指针图
    """
    instant_vector: list[float]  # [x, y]


@app.get("/api/workspace/vectors", response_model=VectorResult)
def get_last_vector(x_player_id: str = Header(default="default", alias="X-Player-Id")) -> VectorResult:
    """读取该玩家最后一次即时向量（供 AI 子模块轮询）

    消费方是前端 services/workspaceApi.ts 的 fetchLastVector()，
    由 stores/workspace.ts 的 setInterval 定时调用。
    多玩家隔离：通过 X-Player-Id 头区分不同玩家的向量。
    """
    last = _session.last_vector(player_id=x_player_id)
    return VectorResult(instant_vector=[last.x, last.y])


@app.post("/api/workspace/vectors", response_model=VectorResult)
def workspace_vectors(
    request: SlotSnapshot,
    x_player_id: str = Header(default="default", alias="X-Player-Id"),
) -> VectorResult:
    """
    配卡运算接口（协议链路3）
    
    新逻辑：调用 MatrixVectorSystem 进行真实计算
    多玩家隔离：通过 X-Player-Id 头区分不同玩家的向量。
    """
    # ========== 模块1: 接收卡槽快照 ==========
    slot_count = len(request.slots)
    print(f'[workspace] 收到卡槽快照 (包含 {slot_count} 张卡牌)')
    print(f'   Slots: {request.slots}')

    # 空卡槽：重置为零向量（协议要求：卡槽清空时向量归零）
    if slot_count == 0:
        print('[workspace] 卡槽为空，返回零向量')
        _session.update_vector(Vector2D(0.0, 0.0), player_id=x_player_id)
        return VectorResult(instant_vector=[0.0, 0.0])

    # ========== 模块2: 调用 MatrixVectorSystem 真实计算 ==========
    # 创建矩阵向量系统实例
    matrix_system = MatrixVectorSystem()
    
    # 调用完整处理流程（自动从后端加载卡牌数据）
    instant_vector = matrix_system.process_snapshot(request.slots, auto_load_cards=True)
    
    print(f'[workspace] 原始计算向量: ({instant_vector.x:.4f}, {instant_vector.y:.4f})')

    # ========== 模块3: 向量处理（统一缩放） ==========
    # 统一除以 50 进行缩放
    processed_x = instant_vector.x / 50
    processed_y = instant_vector.y / 50
    processed_vector = [processed_x, processed_y]
    
    magnitude = (instant_vector.x**2 + instant_vector.y**2)**0.5
    print(f'[workspace] 原始向量模长: {magnitude:.4f}, 统一除以50缩放')
    print(f'[workspace] 处理后向量: ({processed_vector[0]:.4f}, {processed_vector[1]:.4f})')
    
    processed_vec = Vector2D(processed_vector[0], processed_vector[1])

    # ========== 模块4: 记录到 session，供 submit 使用 ==========
    _session.update_vector(processed_vec, player_id=x_player_id)

    # ========== 模块5: 返回响应 ==========
    result = VectorResult(instant_vector=processed_vector)
    print(f'[workspace] 返回向量结果: {result.model_dump()}')

    return result


# ── AI 看山：点评 & 聊天接口 ────────────────────────────────────────


class CommentRequest(BaseModel):
    """看山点评请求

    前端在划线/放卡/结算等事件触发时调用，携带游戏上下文
    """
    event_type: str       # "judge_success" | "judge_fail" | "card_place" | "settle_pass" | "settle_fail"
    article_id: str = ""  # 当前文章 ID（可选，供后续扩展）
    context: dict = {}    # 划线文本/卡牌类型/向量等上下文


class CommentResponse(BaseModel):
    """看山点评响应"""
    text: str


@app.post("/api/ai/comment", response_model=CommentResponse)
def ai_comment(request: CommentRequest) -> CommentResponse:
    """看山一句话点评接口

    接收游戏事件类型和上下文，调用通义千问生成一句话点评。
    API 失败时降级为硬编码消息池。
    """
    result = generate_comment(request.event_type, request.context)
    if result is None:
        result = fallback_comment(request.event_type)
    return CommentResponse(text=result)


class ChatMessage(BaseModel):
    """单条聊天消息"""
    sender: str  # "player" | "ai"
    text: str


class ChatRequest(BaseModel):
    """看山聊天请求"""
    message: str                        # 玩家输入
    history: list[ChatMessage] = []     # 最近对话历史


class ChatResponse(BaseModel):
    """看山聊天响应"""
    reply: str


@app.post("/api/ai/chat", response_model=ChatResponse)
def ai_chat(request: ChatRequest) -> ChatResponse:
    """看山聊天接口

    接收玩家消息和对话历史，调用通义千问生成回复。
    API 失败时降级为硬编码回复池。
    """
    history_dicts = [{"sender": m.sender, "text": m.text} for m in request.history]
    result = generate_chat_reply(request.message, history_dicts)
    if result is None:
        result = fallback_chat_reply()
    return ChatResponse(reply=result)


# ── AI 剧情：局间 ADV 对话生成接口 ───────────────────────


class StoryRequest(BaseModel):
    """局间剧情生成请求

    前端在 round-settlement 屏幕出现时预取，携带本局上下文。
    后端全程无状态：不落盘、不读 session、不做缓存。
    """
    round: int                    # 刚结束的局号（1-5）
    quadrant: str                 # 看山当前所在象限：view | critique | emotion | wasteland
    passed: bool = True           # 本局结算是否通过
    rating: str = ""              # 结算评价文本
    heat: float = 0               # 本局向量热度
    salt: float = 0               # 本局向量盐度
    cards: dict[str, int] = {}    # 四类卡牌计数
    history: list[str] = []       # 最近移动方向


class StoryLine(BaseModel):
    """单句 ADV 对话（字段名与前端 DialogueLine 一致）"""
    speaker: str
    speakerName: str
    text: str


class StoryResponse(BaseModel):
    """剧情生成响应；generated=False 时 lines 为空，由前端降级到本地 A 版剧本"""
    generated: bool
    id: str
    title: str
    lines: list[StoryLine]
    source: str = "ai"
    debug: dict = Field(default_factory=dict)


@app.post("/api/ai/story", response_model=StoryResponse)
def ai_story(request: StoryRequest) -> StoryResponse:
    """局间 ADV 剧情生成接口

    根据本局上下文实时生成一段多角色小剧情（看山 / 旅行者 / 知乎用户A·B·C / 旁白）。
    生成失败时返回 generated=False，不做后端保底（保底剧本唯一来源为前端）。
    """
    started_at = time.perf_counter()
    context = {
        "round": request.round,
        "quadrant": request.quadrant,
        "passed": request.passed,
        "rating": request.rating,
        "heat": request.heat,
        "salt": request.salt,
        "cards": request.cards,
        "history": request.history,
    }
    print(f"[ai_story] 开始生成：{context}")
    lines = generate_story(context)
    latency_ms = int((time.perf_counter() - started_at) * 1000)

    if not lines:
        print(f"[ai_story] 生成失败或不达标，耗时 {latency_ms}ms")
        return StoryResponse(
            generated=False,
            id="",
            title="",
            lines=[],
            source="ai",
            debug={
                "latencyMs": latency_ms,
                "round": request.round,
                "quadrant": request.quadrant,
                "reason": "empty_or_invalid_normalized_lines",
            },
        )

    title = STORY_QUADRANT_NAMES.get(request.quadrant, "旅途插曲")
    story_id = f"ai_story_{request.round}_{uuid4().hex[:8]}"
    print(f"[ai_story] 生成成功：{story_id} {title} lines={len(lines)} latency={latency_ms}ms")
    return StoryResponse(
        generated=True,
        id=story_id,
        title=title,
        lines=[StoryLine(**line) for line in lines],
        source="ai",
        debug={
            "latencyMs": latency_ms,
            "round": request.round,
            "quadrant": request.quadrant,
            "lineCount": len(lines),
            "model": TONGYI_MODEL_STORY,
        },
    )


# ── AI 提示：文章阅读建议接口 ─────────────────────────────


class HintRequest(BaseModel):
    """文章阅读提示请求"""
    scene: str = "article"           # 场景：article（未来可扩展 backpack）
    article_id: str                  # 文章 ID
    mode: str = "rule"               # 模式：rule（规则引擎）| deep（AI 深度分析）


class HintItem(BaseModel):
    """单条阅读建议"""
    start: int                       # 全文偏移（含）
    end: int                         # 全文偏移（不含）
    type: str                        # 卡牌类型：观点卡/情绪卡/漏洞卡/修辞卡
    preview: str                     # 预览文本（前30字）
    reason: str                      # 理由


class HintResponse(BaseModel):
    """提示响应"""
    mode: str                        # rule | deep
    message: str                     # 看山气泡文案
    hints: list[HintItem]            # 建议列表
    analysis: str = ""               # AI 深度分析文本（仅 deep 模式有值）


@app.post("/api/ai/hint", response_model=HintResponse)
def ai_hint(request: HintRequest) -> HintResponse:
    """文章阅读提示接口

    分析文章内容，识别不同卡牌类型的特征段落，生成句子级阅读建议。
    规则引擎模式：毫秒级响应，基于关键词匹配
    AI 深度模式：调用通义千问生成个性化分析（失败降级为规则引擎）
    """
    from game.api.hint_service import get_rule_based_hints

    print(f"[hint] 收到请求：scene={request.scene} article_id={request.article_id} mode={request.mode}")

    # 加载文章
    articles = {article.id: article for article in _load_engine_articles()}
    article = articles.get(request.article_id)

    if article is None:
        print(f"[hint] 文章未找到：{request.article_id}")
        raise HTTPException(status_code=404, detail="Article not found")

    # 规则引擎结果（混合：linespots 精确点 + 关键词特征区）
    linespots = _get_raw_linespots(article)
    print(f"[hint] 读取 linespots {len(linespots)} 个")
    result = get_rule_based_hints(article.content, linespots)
    print(f"[hint] 规则引擎产出 {len(result['hints'])} 条建议")

    # 规则引擎模式
    if request.mode == "rule":
        return HintResponse(
            mode="rule",
            message=result["message"],
            hints=[HintItem(**hint) for hint in result["hints"]],
        )

    # AI 深度模式：规则 hints 作锚点 + AI 生成分析文本
    analysis = generate_deep_reading_hint(article.title, article.content)
    if analysis is None:
        print("[hint] AI 深度分析失败，降级为规则引擎")
        return HintResponse(
            mode="rule",
            message=result["message"],
            hints=[HintItem(**hint) for hint in result["hints"]],
        )

    print(f"[hint] AI 深度分析成功，返回 deep 模式")
    return HintResponse(
        mode="deep",
        message=result["message"],
        hints=[HintItem(**hint) for hint in result["hints"]],
        analysis=analysis,
    )


# ── AI 提示：合成建议深度分析接口 ─────────────────────────


class CompositionHintItemRequest(BaseModel):
    """前端规则引擎产出的单条合成建议"""
    type: str
    title: str
    reason: str
    action: str
    priority: int = 0


class CompositionHintRequest(BaseModel):
    """合成建议深度分析请求"""
    message: str
    items: list[CompositionHintItemRequest] = []
    cardSummary: str = ""
    slotSummary: str = ""
    vector: list[float] = []


class CompositionHintResponse(BaseModel):
    """合成建议深度分析响应"""
    mode: str
    analysis: str


@app.post("/api/ai/composition-hint", response_model=CompositionHintResponse)
def ai_composition_hint(request: CompositionHintRequest) -> CompositionHintResponse:
    """背包合成页的看山深度建议接口。

    前端规则引擎负责判断阵型与风险；后端 AI 只做自然语言补充。
    """
    analysis = generate_deep_composition_hint(
        message=request.message,
        items=[item.model_dump() for item in request.items],
        card_summary=request.cardSummary,
        slot_summary=request.slotSummary,
        vector=request.vector,
    )

    if analysis is None:
        return CompositionHintResponse(
            mode="fallback",
            analysis=fallback_deep_composition_hint(),
        )

    return CompositionHintResponse(mode="deep", analysis=analysis)

