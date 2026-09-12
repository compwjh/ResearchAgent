"""Skill 注册表的领域模型（dataclass，便于序列化与测试）。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class SkillSummary:
    """列表/更新接口的 Skill 投影（不含 body）。"""

    name: str
    description: str
    tools: list[str]
    enabled: bool = True
    # 遗留标记：frontmatter `status: legacy` 透传，供前端提示「遗留（待迁移）」。
    # 不影响 enabled 语义（遗留 Skill 仍可启用/禁用，也不被过滤掉）。
    legacy: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SkillDetail(SkillSummary):
    """详情接口：在投影基础上追加正文 body。"""

    body: str = ""


@dataclass
class SkillRecord:
    """扫描磁盘得到的原始记录，含目录名用于回退。"""

    name: str
    description: str
    tools: list[str]
    body: str
    dir_name: str
    # 同 SkillSummary.legacy：来源为 SKILL.md frontmatter 的 `status` 字段。
    legacy: bool = False


@dataclass
class ToolEntry:
    """Tool 注册项：执行层原子动作，唯一事实源是代码注册（非文档）。

    ``enabled`` 来自状态文件（data/kb/skill-state.json 的 tools 段），
    缺失/损坏时回退 True。``entry`` 指向真实代码入口（模块.函数），
    用于审计与复用追踪，不进入 API 响应。
    """

    name: str
    description: str
    enabled: bool = True
    entry: str = ""
    # function-calling / 计划 JSON 校验用的 JSON Schema（代码即事实源）。
    # properties 声明参数，required 声明必填；RESULT.md 实证「必填字段必须写进 required，
    # 不能靠 description 暗示」。该字段不进入 API 响应（to_dict 省略）。
    parameters: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"name": self.name, "description": self.description, "enabled": self.enabled}
