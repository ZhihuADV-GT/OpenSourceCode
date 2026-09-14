"""
段落模板加载器

职责：
- 从 template_lib/templates.json 加载段落骨架模板
- 按 (角色 × 结构 × 内容类型 × 语气风格) 选择模板
- 提供篇幅档位、织入插槽等参数查询
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field


# ========== 路径配置 ==========

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_TEMPLATE_LIB_DIR = _BACKEND_DIR / "template_lib"
_TEMPLATES_FILE = _TEMPLATE_LIB_DIR / "templates.json"


# ========== 数据类 ==========

@dataclass
class ParagraphTemplate:
    """段落骨架模板"""
    template_id: str
    role: str
    structure: list[str]
    content_type: str
    skeleton: dict
    weave_slots: list[str] = field(default_factory=list)
    length_levels: dict = field(default_factory=dict)
    word_range: dict = field(default_factory=dict)
    tone: Optional[str] = None
    edge_case: Optional[str] = None


# ========== 加载器 ==========

class TemplateLoader:
    """段落模板加载器"""

    def __init__(self):
        self._templates: dict[str, ParagraphTemplate] = {}
        self._loaded = False

    def load(self) -> None:
        """加载模板库（惰性加载，只执行一次）"""
        if self._loaded:
            return

        if not _TEMPLATES_FILE.exists():
            print(f"[template_loader] 模板文件不存在: {_TEMPLATES_FILE}")
            self._loaded = True
            return

        try:
            raw = json.loads(_TEMPLATES_FILE.read_text(encoding="utf-8"))
            for item in raw.get("templates", []):
                tpl = ParagraphTemplate(
                    template_id=item["template_id"],
                    role=item["role"],
                    structure=item.get("structure", ["通用"]),
                    content_type=item.get("content_type", "观点类"),
                    skeleton=item.get("skeleton", {}),
                    weave_slots=item.get("weave_slots", []),
                    length_levels=item.get("length_levels", {}),
                    word_range=item.get("word_range", {}),
                    tone=item.get("tone"),
                    edge_case=item.get("edge_case"),
                )
                self._templates[tpl.template_id] = tpl
            self._loaded = True
            print(f"[template_loader] 已加载 {len(self._templates)} 个段落模板")
        except Exception as e:
            print(f"[template_loader] 加载失败: {e}")
            self._loaded = True

    def get_template(self, template_id: str) -> Optional[ParagraphTemplate]:
        """按 ID 获取模板"""
        self.load()
        return self._templates.get(template_id)

    def select_template(
        self,
        role: str,
        structure: str,
        content_type: str = "观点类",
        tone: Optional[str] = None,
        edge_case: Optional[str] = None,
    ) -> Optional[ParagraphTemplate]:
        """
        按 (角色 × 结构 × 内容类型 × 语气风格 × 边缘情况) 选择模板

        Args:
            role: 段落角色（开头段/论述段/结尾段/破题段/驳斥段/...）
            structure: 文章结构（通用/驳论/并列/递进/总-分-总/总-分/分-总）
            content_type: 内容类型（原因类/机制类/现象类/对比类/例子类/数据类/观点类）
            tone: 语气风格（emotional/critical/None）
            edge_case: 边缘情况（single/multi/transition/None）

        Returns:
            匹配的模板，未找到时回退到通用模板
        """
        self.load()

        # 1. 边缘情况优先
        if edge_case:
            for tpl in self._templates.values():
                if tpl.edge_case == edge_case:
                    return tpl

        # 2. 语气风格变体（仅当 tone 指定时）
        if tone:
            for tpl in self._templates.values():
                if (tpl.tone == tone and
                    tpl.role == role and
                    (structure in tpl.structure or "通用" in tpl.structure)):
                    return tpl

        # 3. 精确匹配：角色 + 结构 + 内容类型
        for tpl in self._templates.values():
            if (tpl.role == role and
                tpl.content_type == content_type and
                (structure in tpl.structure or "通用" in tpl.structure)):
                return tpl

        # 4. 宽松匹配：角色 + 结构（忽略内容类型）
        for tpl in self._templates.values():
            if (tpl.role == role and
                (structure in tpl.structure or "通用" in tpl.structure)):
                return tpl

        # 5. 回退到通用开头/论述/结尾
        fallback_map = {
            "开头段": "para_open",
            "论述段": "para_body_cause",
            "结尾段": "para_close",
            "破题段": "refute_open",
            "驳斥段": "refute_body_cause",
            "立论收束段": "refute_close",
            "并列总起段": "parallel_open",
            "并列论述段": "parallel_body_general",
            "并列汇总段": "parallel_close",
            "递进起始段": "prog_open",
            "递进推进段": "prog_body_deepen",
            "递进到顶段": "prog_close",
            "总起段": "total_open",
            "回扣段": "total_close",
        }
        fallback_id = fallback_map.get(role)
        if fallback_id:
            return self._templates.get(fallback_id)

        return None


# ========== 全局单例 ==========

_loader = TemplateLoader()


def get_template_loader() -> TemplateLoader:
    """获取全局模板加载器单例"""
    return _loader


def select_template(
    role: str,
    structure: str,
    content_type: str = "观点类",
    tone: Optional[str] = None,
    edge_case: Optional[str] = None,
) -> Optional[ParagraphTemplate]:
    """快捷函数：选择模板"""
    return _loader.select_template(role, structure, content_type, tone, edge_case)


def get_template(template_id: str) -> Optional[ParagraphTemplate]:
    """快捷函数：按 ID 获取模板"""
    return _loader.get_template(template_id)
