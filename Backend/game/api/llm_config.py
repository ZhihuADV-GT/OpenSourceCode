"""
LLM 统一配置中心

所有外部模型 API 调用（通义千问等）的密钥、URL、模型名称
均在此处集中管理。修改模型/Key/超时等参数只需改这一个文件。

密钥与 URL 均通过环境变量注入，参见项目根目录 .env.example。

使用方式：
    from game.api.llm_config import LLM_CONFIG
    # 或按需导入具体字段
    from game.api.llm_config import TONGYI_API_KEY, TONGYI_API_BASE_URL
"""

from __future__ import annotations

import os

# ══════════════════════════════════════════════════════════
#  通义千问（DashScope）配置
# ══════════════════════════════════════════════════════════

TONGYI_API_BASE_URL: str = os.getenv("TONGYI_API_BASE_URL", "")
# DashScope 原生格式端点（预处理管道 zhihu_pipeline.py 使用）
DASHSCOPE_NATIVE_API_BASE_URL: str = os.getenv("DASHSCOPE_NATIVE_API_BASE_URL", "")
TONGYI_API_KEY: str = os.getenv("TONGYI_API_KEY", "")


# ══════════════════════════════════════════════════════════
#  备用 LLM 提供商（OpenAI 兼容协议）
#  当阿里云全部模型 failover 失败后，自动降级到此提供商。
# ══════════════════════════════════════════════════════════

BACKUP_LLM_API_BASE_URL: str = os.getenv("BACKUP_LLM_API_BASE_URL", "")
BACKUP_LLM_API_KEY: str = os.getenv("BACKUP_LLM_API_KEY", "")

# 备用提供商的模型名（按优先级排列）
# 根据实际提供商支持的模型调整（见 OpenAI 兼容端点可用模型列表）
BACKUP_MODEL_ANNOTATE: list[str] = ["gpt-4o-mini", "gpt-3.5-turbo"]         # 标注用较重模型
BACKUP_MODEL_CHAT: list[str] = ["gpt-4o-mini", "gpt-3.5-turbo"]              # 点评 & 聊天（轻量快速）
BACKUP_MODEL_STORY: list[str] = ["gpt-4o-mini", "gpt-3.5-turbo"]             # 剧情生成（成本优先）
BACKUP_MODEL_HINT: list[str] = ["gpt-4o-mini", "gpt-3.5-turbo"]              # 阅读深度分析（成本优先）
BACKUP_MODEL_DYNAMIC_CARD: list[str] = ["gpt-4o-mini", "gpt-3.5-turbo"]      # 动态卡判型（成本优先）


# ══════════════════════════════════════════════════════════
#  第二备用 LLM 提供商（DeepSeek，OpenAI 兼容协议）
#  当第一备用也全部失败后，自动降级到此提供商（优先级最低）。
# ══════════════════════════════════════════════════════════

DEEPSEEK_API_BASE_URL: str = os.getenv("DEEPSEEK_API_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")

DEEPSEEK_MODEL_ANNOTATE: list[str] = ["deepseek-flash"]
DEEPSEEK_MODEL_CHAT: list[str] = ["deepseek-flash"]
DEEPSEEK_MODEL_STORY: list[str] = ["deepseek-flash"]
DEEPSEEK_MODEL_HINT: list[str] = ["deepseek-flash"]
DEEPSEEK_MODEL_DYNAMIC_CARD: list[str] = ["deepseek-flash"]


# 文章标注用较重模型；点评/聊天用轻量模型（成本低、速度快）
TONGYI_MODEL_ANNOTATE: list[str] = ["qwen3.5-35b-a3b", "qwen3.5-plus-2026-04-20", "qwen3.5-122b-a10b", "qwen3.5-397b-a17b", "qwen3.5-flash", "qwen3.5-plus"]    # 用于预处理管道文章标注
TONGYI_MODEL_CHAT: list[str] = ["qwen3.5-35b-a3b", "qwen3.5-plus-2026-04-20", "qwen3.5-122b-a10b", "qwen3.5-397b-a17b", "qwen3.5-flash", "qwen3.5-plus"]       # 用于看山实时点评 & 聊天
TONGYI_MODEL_STORY: list[str] = ["qwen3.5-35b-a3b", "qwen3.5-plus-2026-04-20", "qwen3.5-122b-a10b", "qwen3.5-397b-a17b", "qwen3.5-flash", "qwen3.5-plus"]      # 用于局间 ADV 剧情生成（成本优先）
TONGYI_MODEL_HINT: list[str] = ["qwen3.5-35b-a3b", "qwen3.5-plus-2026-04-20", "qwen3.5-122b-a10b", "qwen3.5-397b-a17b", "qwen3.5-flash", "qwen3.5-plus"]       # 用于阅读提示深度分析（成本优先）
TONGYI_MODEL_DYNAMIC_CARD: list[str] = ["qwen3.5-35b-a3b", "qwen3.5-plus-2026-04-20", "qwen3.5-122b-a10b", "qwen3.5-397b-a17b", "qwen3.5-flash", "qwen3.5-plus"]  # 用于玩家动态划线的判型与选文（成本优先）

# ── 超时（秒） ──────────────────────────────────────────
TONGYI_TIMEOUT_ANNOTATE: int = 30   # 标注 Prompt 长，给足时间
TONGYI_TIMEOUT_COMMENT: int = 8     # 一句话点评，快速返回
TONGYI_TIMEOUT_CHAT: int = 15       # 聊天回复，适中
TONGYI_TIMEOUT_STORY: int = 12      # 剧情 5-8 句，前端在结算界面预取
TONGYI_TIMEOUT_HINT: int = 15       # 阅读深度分析，适中
# 动态卡判定：输出只是一个短 JSON 对象，但前端全局 axios 超时是 5s，
# 该接口在前端单独覆盖为 20s，后端预算必须留在这个包络内
TONGYI_TIMEOUT_DYNAMIC_CARD: int = 15

# ── 剧情生成参数 ─────────────────────
STORY_MAX_TOKENS: int = 1024        # 5-8 句 JSON 数组的输出上限（600 太紧，中文台词+JSON 结构容易超限被截断）
STORY_TEMPERATURE: float = 0.95     # 即兴生成，需要多样性

# ── 阅读提示深度分析参数 ─────────────
HINT_MAX_TOKENS: int = 300          # 深度分析输出上限
HINT_TEMPERATURE: float = 0.7       # 分析需要一定稳定性

# ── 动态卡牌判定参数 ─────────────────
DYNAMIC_CARD_MAX_TOKENS: int = 300  # 输出只是一个短 JSON 对象
# 低温是双重的：既要同一段选区反复划得到稳定判型，
# 也要压低 JSON 格式跑偏的概率（该接口最常见的失败模式是解析失败而非超时）。
# 与 STORY_TEMPERATURE=0.95、call_tongyi 默认 0.85 的方向相反，是刻意的。
DYNAMIC_CARD_TEMPERATURE: float = 0.2
# 每局动态卡上限。按 round 分区计数（不是清缓存），幂等且乱序安全。
# 取值依据：矩阵 4×5=20 格、背包容量 20、每篇预设 linespot 5-8 个，
# 留出 6 格给玩家自由划线，不至于把预设卡挤出背包。
DYNAMIC_CARD_QUOTA_PER_ROUND: int = 6


# ══════════════════════════════════════════════════════════
#  知乎 API 配置（预处理管道使用）
# ══════════════════════════════════════════════════════════

ZHIHU_API_BASE_URL: str = "https://developer.zhihu.com/api/v1"
# 兼容旧预处理脚本变量名，但实际从官方 Access Secret 环境变量读取。
ZHIHU_ACCESS_TOKEN: str = os.getenv("ZHIHU_ACCESS_SECRET", os.getenv("ZHIHU_ACCESS_TOKEN", "")).strip()


# ══════════════════════════════════════════════════════════
#  聚合字典（方便旧代码 CONFIG["xxx"] 风格访问）
# ══════════════════════════════════════════════════════════

LLM_CONFIG: dict = {
    "TONGYI_API_BASE_URL": TONGYI_API_BASE_URL,
    "DASHSCOPE_NATIVE_API_BASE_URL": DASHSCOPE_NATIVE_API_BASE_URL,
    "TONGYI_API_KEY": TONGYI_API_KEY,
    "TONGYI_MODEL_ANNOTATE": TONGYI_MODEL_ANNOTATE,
    "TONGYI_MODEL_CHAT": TONGYI_MODEL_CHAT,
    "TONGYI_MODEL_STORY": TONGYI_MODEL_STORY,
    "TONGYI_MODEL_HINT": TONGYI_MODEL_HINT,
    "TONGYI_MODEL_DYNAMIC_CARD": TONGYI_MODEL_DYNAMIC_CARD,
    "TONGYI_TIMEOUT_STORY": TONGYI_TIMEOUT_STORY,
    "TONGYI_TIMEOUT_HINT": TONGYI_TIMEOUT_HINT,
    "TONGYI_TIMEOUT_DYNAMIC_CARD": TONGYI_TIMEOUT_DYNAMIC_CARD,
    "STORY_MAX_TOKENS": STORY_MAX_TOKENS,
    "STORY_TEMPERATURE": STORY_TEMPERATURE,
    "HINT_MAX_TOKENS": HINT_MAX_TOKENS,
    "HINT_TEMPERATURE": HINT_TEMPERATURE,
    "DYNAMIC_CARD_MAX_TOKENS": DYNAMIC_CARD_MAX_TOKENS,
    "DYNAMIC_CARD_TEMPERATURE": DYNAMIC_CARD_TEMPERATURE,
    "DYNAMIC_CARD_QUOTA_PER_ROUND": DYNAMIC_CARD_QUOTA_PER_ROUND,
    # ── 备用提供商 ──
    "BACKUP_LLM_API_BASE_URL": BACKUP_LLM_API_BASE_URL,
    "BACKUP_LLM_API_KEY": BACKUP_LLM_API_KEY,
    "BACKUP_MODEL_ANNOTATE": BACKUP_MODEL_ANNOTATE,
    "BACKUP_MODEL_CHAT": BACKUP_MODEL_CHAT,
    "BACKUP_MODEL_STORY": BACKUP_MODEL_STORY,
    "BACKUP_MODEL_HINT": BACKUP_MODEL_HINT,
    "BACKUP_MODEL_DYNAMIC_CARD": BACKUP_MODEL_DYNAMIC_CARD,
    # ── 第二备用提供商（DeepSeek） ──
    "DEEPSEEK_API_BASE_URL": DEEPSEEK_API_BASE_URL,
    "DEEPSEEK_API_KEY": DEEPSEEK_API_KEY,
    "DEEPSEEK_MODEL_ANNOTATE": DEEPSEEK_MODEL_ANNOTATE,
    "DEEPSEEK_MODEL_CHAT": DEEPSEEK_MODEL_CHAT,
    "DEEPSEEK_MODEL_STORY": DEEPSEEK_MODEL_STORY,
    "DEEPSEEK_MODEL_HINT": DEEPSEEK_MODEL_HINT,
    "DEEPSEEK_MODEL_DYNAMIC_CARD": DEEPSEEK_MODEL_DYNAMIC_CARD,
    "ZHIHU_API_BASE_URL": ZHIHU_API_BASE_URL,
    "ZHIHU_ACCESS_TOKEN": ZHIHU_ACCESS_TOKEN,
}
