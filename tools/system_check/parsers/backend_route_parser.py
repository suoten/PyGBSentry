from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Optional

from tools.system_check.parsers.python_ast_parser import PythonAstParser
from tools.system_check.shared.models import RouteInfo


class BackendRouteParser:
    _HTTP_METHODS = {"get", "post", "put", "delete", "patch", "head", "options"}
    _INCLUDE_ROUTER_RE = re.compile(r"(?:include_router|_mount)\s*\(")
    _PREFIX_RE = re.compile(r"prefix\s*=\s*['\"]([^'\"]+)['\"]")
    _CONDITIONAL_RE = re.compile(r"is_server_edition")
    _DEPRECATED_RE = re.compile(r"deprecated|DEPRECATED", re.IGNORECASE)

    @classmethod
    def parse_runtime_routes(cls, app_module_path: str = "app.main") -> list[dict]:
        """通过导入 FastAPI app 运行时枚举所有注册路由。

        比AST解析更准确，能处理 _mount() 等间接调用。
        """
        try:
            import importlib
            mod = importlib.import_module(app_module_path)
            app = getattr(mod, "app", None)
            if app is None:
                return []
            routes = []
            from fastapi.routing import APIRoute, APIWebSocketRoute
            for route in app.routes:
                if isinstance(route, APIRoute):
                    routes.append({
                        "method": list(route.methods)[0] if route.methods else "GET",
                        "path": route.path,
                        "function_name": route.name or "",
                        "is_deprecated": False,
                    })
                elif isinstance(route, APIWebSocketRoute):
                    routes.append({
                        "method": "WEBSOCKET",
                        "path": route.path,
                        "function_name": route.name or "",
                        "is_deprecated": False,
                    })
            return routes
        except Exception:
            return []

    @classmethod
    def parse_api_registration(cls, api_py_path: str | Path) -> list[dict]:
        api_path = Path(api_py_path)
        if not api_path.exists():
            return []

        source = api_path.read_text(encoding="utf-8", errors="replace")
        tree = PythonAstParser.parse_file(str(api_path))
        if tree is None:
            return []

        registrations: list[dict] = []
        lines = source.splitlines()
        in_server_block = False

        for i, line in enumerate(lines):
            stripped = line.strip()

            if "if is_server_edition" in stripped or "if not is_server_edition" in stripped:
                in_server_block = "if is_server_edition" in stripped
                continue

            if in_server_block and stripped in (")", "else:"):
                if stripped == "else:":
                    in_server_block = False
                continue
            if not in_server_block and stripped == ")":
                continue

            if cls._INCLUDE_ROUTER_RE.search(stripped):
                prefix_match = cls._PREFIX_RE.search(stripped)
                prefix = prefix_match.group(1) if prefix_match else ""

                router_var = ""
                for arg in stripped.split(","):
                    arg = arg.strip()
                    if arg.startswith("router") or arg.startswith("r_"):
                        router_var = arg.split("=")[1].strip() if "=" in arg else arg
                        break
                    if not arg.startswith("prefix") and not arg.startswith("tags") and not arg.startswith("dependencies"):
                        if not arg.startswith(")") and not arg.startswith("include_router") and not arg.startswith("_mount"):
                            router_var = arg

                edition_scope = "server" if in_server_block else "both"
                if "if not is_server_edition" in lines[max(0, i - 1)] or any(
                    "if not is_server_edition" in lines[j] for j in range(max(0, i - 3), i)
                ):
                    edition_scope = "oss"

                registrations.append({
                    "prefix": prefix,
                    "router_var": router_var,
                    "line_number": i + 1,
                    "edition_scope": edition_scope,
                })

        return registrations

    @classmethod
    def parse_endpoint_routes(
        cls, endpoint_module_path: str | Path, prefix: str = ""
    ) -> list[RouteInfo]:
        module_path = Path(endpoint_module_path)
        if not module_path.exists():
            return []

        tree = PythonAstParser.parse_file(str(module_path))
        if tree is None:
            return []

        source_lines = PythonAstParser.get_source_lines(str(module_path))
        routes: list[RouteInfo] = []

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            for deco in node.decorator_list:
                method, path_str = cls._parse_route_decorator(deco)
                if method is None:
                    continue

                full_path = prefix + path_str
                is_deprecated = cls._is_deprecated(node, source_lines)
                has_pydantic = cls._has_pydantic_params(node)
                response_model = cls._get_response_model(deco)

                routes.append(RouteInfo(
                    method=method.upper(),
                    path=path_str,
                    function_name=node.name,
                    file_path=str(module_path),
                    line_number=node.lineno,
                    prefix=prefix,
                    full_path=full_path,
                    has_pydantic=has_pydantic,
                    response_model=response_model,
                    is_deprecated=is_deprecated,
                ))

        return routes

    @classmethod
    def parse_all_routes(cls, api_py_path: str | Path) -> list[RouteInfo]:
        api_path = Path(api_py_path)
        if not api_path.exists():
            return []

        registrations = cls.parse_api_registration(api_path)
        all_routes: list[RouteInfo] = []
        api_dir = api_path.parent

        for reg in registrations:
            router_var = reg.get("router_var", "")
            prefix = reg.get("prefix", "")
            edition_scope = reg.get("edition_scope", "both")

            module_path = cls._resolve_router_module(api_dir, router_var)
            if module_path and module_path.exists():
                routes = cls.parse_endpoint_routes(module_path, prefix)
                for r in routes:
                    r.edition_scope = edition_scope
                all_routes.extend(routes)

        return all_routes

    @classmethod
    def _parse_route_decorator(cls, deco: ast.expr) -> tuple[Optional[str], str]:
        method: Optional[str] = None
        path_str = "/"

        if isinstance(deco, ast.Call):
            func = deco.func
            if isinstance(func, ast.Attribute) and func.attr in cls._HTTP_METHODS:
                method = func.attr
            elif isinstance(func, ast.Name) and func.id in cls._HTTP_METHODS:
                method = func.id

            if method and deco.args:
                path_str = cls._extract_string(deco.args[0])
            if method and not deco.args:
                for kw in deco.keywords:
                    if kw.arg == "path" or kw.arg == "summary":
                        path_str = cls._extract_string(kw.value)
                        break

        elif isinstance(deco, ast.Attribute) and deco.attr in cls._HTTP_METHODS:
            method = deco.attr

        return method, path_str

    @classmethod
    def _extract_string(cls, node: ast.expr) -> str:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.JoinedStr):
            parts: list[str] = []
            for v in node.values:
                if isinstance(v, ast.Constant) and isinstance(v.value, str):
                    parts.append(v.value)
                elif isinstance(v, ast.FormattedValue):
                    parts.append("{param}")
            return "".join(parts)
        return "/"

    @classmethod
    def _resolve_router_module(cls, api_dir: Path, router_var: str) -> Optional[Path]:
        name = router_var.replace("_router", "").replace("router", "").strip("_")
        if not name:
            return None

        endpoints_dir = api_dir / "endpoints"

        candidates = [
            endpoints_dir / f"{name}.py",
            endpoints_dir / name / "_common.py",
            endpoints_dir / name,
        ]

        for candidate in candidates:
            if candidate.exists():
                return candidate

        if endpoints_dir.exists():
            for f in endpoints_dir.iterdir():
                if f.is_dir() and f.name == name:
                    for sub in f.glob("*.py"):
                        if sub.name != "__init__.py" and not sub.name.startswith("_"):
                            return sub
                    break

        return None

    @classmethod
    def _is_deprecated(cls, node: ast.FunctionDef | ast.AsyncFunctionDef, source_lines: list[str]) -> bool:
        for deco in node.decorator_list:
            if isinstance(deco, ast.Name) and deco.id == "deprecated":
                return True
            if isinstance(deco, ast.Call) and isinstance(deco.func, ast.Name) and deco.func.id == "deprecated":
                return True
        if node.lineno > 0:
            for i in range(max(0, node.lineno - 2), node.lineno):
                if i < len(source_lines) and cls._DEPRECATED_RE.search(source_lines[i]):
                    return True
        return False

    @classmethod
    def _has_pydantic_params(cls, node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
        for arg in node.args.args:
            if arg.arg in ("self", "cls", "request", "response", "db", "current_user", "deps"):
                continue
            if arg.annotation:
                ann_str = ast.dump(arg.annotation)
                if "BaseModel" in ann_str or "Schema" in ann_str or "Create" in ann_str or "Update" in ann_str:
                    return True
        return False

    @classmethod
    def _get_response_model(cls, deco: ast.expr) -> Optional[str]:
        if isinstance(deco, ast.Call):
            for kw in deco.keywords:
                if kw.arg == "response_model":
                    return cls._extract_type_name(kw.value)
        return None

    @classmethod
    def _extract_type_name(cls, node: ast.expr) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        if isinstance(node, ast.Subscript):
            return cls._extract_type_name(node.value)
        return ""
