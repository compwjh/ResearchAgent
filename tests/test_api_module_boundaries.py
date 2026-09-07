"""Spec017 模块边界静态检查（AST 扫描，不 import 被检查的模块）。

覆盖两条规则：
1. 必改项 4：路由不得持有 TaskStore / PaperDiscoveryStore /
   PaperImportBatchStore / PaperBrowserManager 等模块级单例——
   即 backend/app/api/ 下任意 .py 的模块顶层不得出现
   `x = TaskStore()` 这类单例实例化赋值。
2. 静态边界检查规则：backend/app/platform/ 不得 import
   services / domain / api / graphs 等业务模块，只能依赖自身
   （backend.app.platform.*）、基础层（如 core 配置）/ 第三方/标准库。
   规则原文的禁业务模块集合即 {services, domain, api, graphs}；core 属
   基础基础设施（config 等），不在该禁集合内，故允许。

用 ast.parse 读源码文本做静态断言，避免 import 副作用；
仓库根用 Path(__file__).resolve().parents[1] 推导，不写死绝对路径。
"""
import ast
from pathlib import Path

# 禁止在 api 层模块顶层实例化的业务单例类名（必改项 4）。
_FORBIDDEN_SINGLETONS = {
    "TaskStore",
    "PaperDiscoveryStore",
    "PaperImportBatchStore",
    "PaperBrowserManager",
}

# 禁止 platform 层依赖的业务子包前缀（静态边界检查规则）。
# 只禁 rules 里明确列举的业务模块 {services, domain, api, graphs}；
# core 等基础层（config 等）与 backend.app.platform.* 自身、第三方/
# 标准库均允许。
_FORBIDDEN_PLATFORM_SUBPACKAGES = (
     "backend.app.services",
     "backend.app.domain",
     "backend.app.api",
     "backend.app.graphs",
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_API_DIR = _REPO_ROOT / "backend" / "app" / "api"
_PLATFORM_DIR = _REPO_ROOT / "backend" / "app" / "platform"


def _py_files(directory: Path):
    """返回目录下所有 .py（跳过 __pycache__），按路径排序保证稳定。"""
    if not directory.is_dir():
        return []
    return sorted(
        p
        for p in directory.rglob("*.py")
        if "__pycache__" not in p.parts
     )


def test_api_has_no_module_level_singleton_instances():
    """必改项 4：api 层模块顶层不得实例化业务单例。

    只遍历每个文件 ast 的 tree.body（模块顶层一层，不下钻函数/类），
    对 Assign 节点若 value 是 Call、其 func 是 Name、且类名在禁止集合中，
    记为违规。删除 routes_kb 的死单例后该列表应为空。
    """
    violations = []
    for path in _py_files(_API_DIR):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            value = node.value
            is_forbidden = (
                isinstance(value, ast.Call)
                and isinstance(value.func, ast.Name)
                and value.func.id in _FORBIDDEN_SINGLETONS
            )
            if is_forbidden:
                violations.append(f"{path}:{node.lineno}:{value.func.id}")
    assert not violations, (
        "api 层仍存在模块级单例实例化赋值（违反 Spec017 必改项 4）:\n"
         + "\n".join(violations)
    )


def _module_names_from(node: ast.AST):
    """从一个 import 节点取出全部被 import 的模块名。"""
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if isinstance(node, ast.ImportFrom):
        return [node.module or ""]
    return []


def _blocks_forbidden(m: str) -> bool:
    """模块名是否命中被禁的业务子包（前缀或其后接点，避免误伤同名更长包）。"""
    return any(
        m == prefix or m.startswith(prefix + ".")
        for prefix in _FORBIDDEN_PLATFORM_SUBPACKAGES
    )


def test_platform_does_not_import_business_modules():
    """静态边界检查规则：platform 不得 import services/domain/api/graphs 等业务模块。

    用 ast.walk 收集全部 Import/ImportFrom 的模块名；若命中禁业务子包集合
     （services/domain/api/graphs）则记为违规。core 等基础层与
    backend.app.platform.* 自身、第三方/标准库均允许。当前应全部通过。
    """
    violations = []
    for path in _py_files(_PLATFORM_DIR):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            for mod in _module_names_from(node):
                if _blocks_forbidden(mod):
                    violations.append(f"{path}:{node.lineno}:{mod}")
    assert not violations, (
         "platform 层 import 了业务模块（违反 Spec017 静态边界检查规则）:\n"
         + "\n".join(violations)
    )
