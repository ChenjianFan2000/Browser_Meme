"""Observation-policy checks; Linux namespaces provide the separate OS boundary.

This deliberately supports native Playwright locators, not website actions.
Scripts cannot inspect runtime internals, raw traces, client code or HTTP APIs.
"""
import ast

MODULES = {"json", "re", "math", "statistics", "collections"}
ATTRIBUTES = set("""
page fixture origin expect observe network note prediction predict intent
goto reload go_back go_forward title url content inner_text text_content inner_html
locator get_by_role get_by_text get_by_label get_by_placeholder get_by_test_id
get_by_alt_text get_by_title frame_locator filter first last nth all count
click dblclick fill press check uncheck set_checked select_option hover focus
is_visible is_enabled is_disabled is_checked is_editable is_hidden get_attribute
input_value all_inner_texts all_text_contents wait_for wait_for_load_state
scroll_into_view_if_needed wait_for_timeout keyboard mouse wheel type move
append extend pop get items keys values update setdefault copy sort index count
lower upper strip lstrip rstrip split rsplit splitlines join replace startswith endswith
find rfind encode decode isdigit isalpha isalnum casefold capitalize
match search fullmatch findall finditer sub escape compile group groups groupdict
dumps loads ceil floor sqrt isfinite mean median Counter most_common
""".split())
DENIED_NAMES = {"eval", "exec", "compile", "open", "input", "globals", "locals",
                "vars", "dir", "getattr", "setattr", "delattr", "type", "object",
                "super", "help", "breakpoint", "memoryview", "__import__"}


def validate_script(source: str, *, module_names=()):
    if len(source.encode()) > 128 * 1024:
        raise ValueError("script exceeds 128 KiB")
    tree = ast.parse(source)
    modules = MODULES | set(module_names)
    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.AsyncFunctionDef, ast.AsyncFor, ast.AsyncWith,
                             ast.Global, ast.Nonlocal, ast.Delete, ast.Yield, ast.YieldFrom)):
            raise ValueError(f"observation policy excludes {type(node).__name__}")
        if isinstance(node, ast.Name) and (node.id.startswith("_") or node.id in DENIED_NAMES):
            raise ValueError(f"observation policy excludes name {node.id}")
        if isinstance(node, ast.Attribute) and node.attr not in ATTRIBUTES:
            raise ValueError(f"observation policy excludes attribute {node.attr}")
        if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign, ast.NamedExpr)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(item, ast.Attribute) for target in targets for item in ast.walk(target)):
                raise ValueError("attribute mutation is not permitted")
        if isinstance(node, ast.Import):
            if any(alias.name not in modules for alias in node.names):
                raise ValueError("only registered pure Python modules may be imported")
        if isinstance(node, ast.ImportFrom):
            if node.level or node.module not in modules or any(a.name.startswith("_") for a in node.names):
                raise ValueError("unregistered import")
        if isinstance(node, (ast.FunctionDef, ast.Lambda)):
            if isinstance(node, ast.FunctionDef) and node.decorator_list:
                raise ValueError("function decorators are excluded")
        if isinstance(node, ast.With):
            raise ValueError("context managers are reserved to the trusted runtime")
    return tree
