import re
from dataclasses import dataclass, field
from pathlib import Path

from tree_sitter import Language, Parser
import tree_sitter_python
import tree_sitter_javascript
import tree_sitter_typescript
import tree_sitter_go
import tree_sitter_java
import tree_sitter_rust
import tree_sitter_c_sharp

try:
    import tree_sitter_dart
except ImportError:
    tree_sitter_dart = None  # optional on Windows (no wheel)

try:
    import tree_sitter_dockerfile
except ImportError:
    tree_sitter_dockerfile = None  # optional on Windows (no wheel)

from server.indexer.walker import detect_language

_LANGUAGES: dict[str, Language] = {}


def _get_language(name: str) -> Language | None:
    if name not in _LANGUAGES:
        loaders = {
            "python": tree_sitter_python.language,
            "javascript": tree_sitter_javascript.language,
            "typescript": tree_sitter_typescript.language_typescript,
            "go": tree_sitter_go.language,
            "java": tree_sitter_java.language,
            "rust": tree_sitter_rust.language,
            "csharp": tree_sitter_c_sharp.language,
        }
        if tree_sitter_dart is not None:
            loaders["dart"] = tree_sitter_dart.language
        if tree_sitter_dockerfile is not None:
            loaders["dockerfile"] = tree_sitter_dockerfile.language
        fn = loaders.get(name)
        if fn:
            _LANGUAGES[name] = Language(fn())
    return _LANGUAGES.get(name)


@dataclass
class ParsedSymbol:
    name: str
    kind: str
    start_line: int
    end_line: int
    signature: str | None = None


@dataclass
class ParsedImport:
    source: str
    imported_name: str | None = None
    line: int | None = None


@dataclass
class ParsedRoute:
    method: str | None
    path: str
    handler: str | None = None
    line: int | None = None


@dataclass
class ParseResult:
    symbols: list[ParsedSymbol] = field(default_factory=list)
    imports: list[ParsedImport] = field(default_factory=list)
    routes: list[ParsedRoute] = field(default_factory=list)
    line_count: int = 0


def _lang_parser(language: str) -> Parser | None:
    lang = _get_language(language)
    if not lang:
        return None
    return Parser(lang)


def _node_text(source: bytes, node) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _line(node) -> int:
    return node.start_point[0] + 1


def _is_component_name(name: str) -> bool:
    return bool(name) and name[0].isupper() and not name.isupper()


def _extract_routes_from_text(content: str, line_offset: int = 0) -> list[ParsedRoute]:
    routes: list[ParsedRoute] = []
    patterns = [
        (r'@(?:Get|Post|Put|Delete|Patch)Mapping\s*\(\s*"([^"]+)"', None),
        (r'@(\w+)Mapping\s*\(\s*"([^"]+)"', None),
        (r'\[Http(Get|Post|Put|Delete|Patch)(?:\("([^"]+)"\))?\]', None),
        (r'#\[(\w+)\s*\(\s*"([^"]+)"\s*\)\]', None),
        (r'\.route\s*\(\s*"([^"]+)"', "GET"),
        (r'@(GET|POST|PUT|DELETE|PATCH)\s*\(\s*[\'"]([^\'"]+)[\'"]', None),
    ]
    for i, line in enumerate(content.splitlines(), start=1):
        for pat, default_method in patterns:
            m = re.search(pat, line, re.IGNORECASE)
            if not m:
                continue
            groups = m.groups()
            if len(groups) == 1:
                routes.append(ParsedRoute("GET", groups[0], line=i + line_offset))
            elif len(groups) == 2:
                method = (groups[0] or default_method or "GET").upper()
                path = groups[1] or "/*"
                if "Mapping" in method:
                    method = method.replace("MAPPING", "").upper() or "GET"
                routes.append(ParsedRoute(method, path, line=i + line_offset))
    return routes


def parse_python(source: bytes, tree) -> ParseResult:
    result = ParseResult(line_count=source.count(b"\n") + 1)
    root = tree.root_node

    def walk(node):
        if node.type == "function_definition":
            name_node = node.child_by_field_name("name")
            params = node.child_by_field_name("parameters")
            if name_node:
                name = _node_text(source, name_node)
                sig = name + (_node_text(source, params) if params else "")
                result.symbols.append(ParsedSymbol(name, "function", _line(node), node.end_point[0] + 1, sig))
        elif node.type == "class_definition":
            name_node = node.child_by_field_name("name")
            if name_node:
                result.symbols.append(
                    ParsedSymbol(_node_text(source, name_node), "class", _line(node), node.end_point[0] + 1)
                )
        elif node.type == "import_statement":
            text = _node_text(source, node).strip()
            m = re.match(r"import\s+([\w.]+)", text)
            result.imports.append(ParsedImport(m.group(1) if m else text, line=_line(node)))
        elif node.type == "import_from_statement":
            module = node.child_by_field_name("module_name")
            if module:
                result.imports.append(ParsedImport(_node_text(source, module), line=_line(node)))
        elif node.type == "decorated_definition":
            for child in node.children:
                if child.type == "decorator":
                    text = _node_text(source, child)
                    for pattern in [
                        r'@app\.(get|post|put|delete|patch)\(["\']([^"\']+)["\']',
                        r'@router\.(get|post|put|delete|patch)\(["\']([^"\']+)["\']',
                    ]:
                        m = re.search(pattern, text)
                        if m:
                            result.routes.append(ParsedRoute(m.group(1).upper(), m.group(2), line=_line(child)))
        for child in node.children:
            walk(child)

    walk(root)
    return result


def parse_js_ts(source: bytes, tree, is_tsx: bool = False) -> ParseResult:
    result = ParseResult(line_count=source.count(b"\n") + 1)
    text = source.decode("utf-8", errors="replace")
    root = tree.root_node

    def walk(node):
        t = node.type
        if t in {"function_declaration", "method_definition", "arrow_function", "function_expression"}:
            name_node = node.child_by_field_name("name")
            if name_node:
                name = _node_text(source, name_node)
                kind = "component" if _is_component_name(name) else ("method" if t == "method_definition" else "function")
                result.symbols.append(ParsedSymbol(name, kind, _line(node), node.end_point[0] + 1))
        elif t == "lexical_declaration":
            text_node = _node_text(source, node)
            m = re.search(r"const\s+([A-Z]\w*)\s*=", text_node)
            if m:
                result.symbols.append(ParsedSymbol(m.group(1), "component", _line(node), node.end_point[0] + 1))
        elif t == "class_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = _node_text(source, name_node)
                kind = "component" if _is_component_name(name) else "class"
                result.symbols.append(ParsedSymbol(name, kind, _line(node), node.end_point[0] + 1))
        elif t == "interface_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                result.symbols.append(
                    ParsedSymbol(_node_text(source, name_node), "interface", _line(node), node.end_point[0] + 1)
                )
        elif t == "import_statement":
            source_node = node.child_by_field_name("source")
            if source_node:
                result.imports.append(
                    ParsedImport(_node_text(source, source_node).strip("'\""), line=_line(node))
                )
        elif t == "call_expression":
            fn = node.child_by_field_name("function")
            args = node.child_by_field_name("arguments")
            if fn and args:
                fn_text = _node_text(source, fn)
                args_text = _node_text(source, args)
                for method in ["get", "post", "put", "delete", "patch", "all", "use"]:
                    if f".{method}(" in fn_text or fn_text == method:
                        m = re.search(r'["\']([^"\']+)["\']', args_text)
                        if m:
                            result.routes.append(ParsedRoute(method.upper(), m.group(1), line=_line(node)))
        for child in node.children:
            walk(child)

    walk(root)
    result.routes.extend(_extract_routes_from_text(text))
    return result


def parse_go(source: bytes, tree) -> ParseResult:
    result = ParseResult(line_count=source.count(b"\n") + 1)
    text = source.decode("utf-8", errors="replace")
    root = tree.root_node

    def walk(node):
        if node.type == "function_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                result.symbols.append(
                    ParsedSymbol(_node_text(source, name_node), "function", _line(node), node.end_point[0] + 1)
                )
        elif node.type == "method_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                result.symbols.append(
                    ParsedSymbol(_node_text(source, name_node), "method", _line(node), node.end_point[0] + 1)
                )
        elif node.type == "type_declaration":
            for child in node.children:
                if child.type == "type_spec":
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        result.symbols.append(
                            ParsedSymbol(_node_text(source, name_node), "type", _line(child), child.end_point[0] + 1)
                        )
        elif node.type == "import_declaration":
            result.imports.append(ParsedImport(_node_text(source, node).strip(), line=_line(node)))
        for child in node.children:
            walk(child)

    walk(root)
    result.routes.extend(_extract_routes_from_text(text))
    return result


def parse_java(source: bytes, tree) -> ParseResult:
    result = ParseResult(line_count=source.count(b"\n") + 1)
    text = source.decode("utf-8", errors="replace")
    root = tree.root_node

    def walk(node):
        if node.type == "class_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = _node_text(source, name_node)
                result.symbols.append(ParsedSymbol(name, "class", _line(node), node.end_point[0] + 1))
        elif node.type in {"method_declaration", "constructor_declaration"}:
            name_node = node.child_by_field_name("name")
            if name_node:
                result.symbols.append(
                    ParsedSymbol(_node_text(source, name_node), "method", _line(node), node.end_point[0] + 1)
                )
        elif node.type == "interface_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                result.symbols.append(
                    ParsedSymbol(_node_text(source, name_node), "interface", _line(node), node.end_point[0] + 1)
                )
        elif node.type == "import_declaration":
            result.imports.append(ParsedImport(_node_text(source, node).strip(), line=_line(node)))
        for child in node.children:
            walk(child)

    walk(root)
    result.routes.extend(_extract_routes_from_text(text))
    return result


def parse_rust(source: bytes, tree) -> ParseResult:
    result = ParseResult(line_count=source.count(b"\n") + 1)
    text = source.decode("utf-8", errors="replace")
    root = tree.root_node

    def walk(node):
        t = node.type
        if t == "function_item":
            name_node = node.child_by_field_name("name")
            if name_node:
                result.symbols.append(
                    ParsedSymbol(_node_text(source, name_node), "function", _line(node), node.end_point[0] + 1)
                )
        elif t == "struct_item":
            name_node = node.child_by_field_name("name")
            if name_node:
                result.symbols.append(
                    ParsedSymbol(_node_text(source, name_node), "struct", _line(node), node.end_point[0] + 1)
                )
        elif t == "impl_item":
            type_node = node.child_by_field_name("type")
            if type_node:
                result.symbols.append(
                    ParsedSymbol(_node_text(source, type_node), "impl", _line(node), node.end_point[0] + 1)
                )
        elif t == "use_declaration":
            result.imports.append(ParsedImport(_node_text(source, node).strip(), line=_line(node)))
        elif t == "mod_item":
            name_node = node.child_by_field_name("name")
            if name_node:
                result.symbols.append(
                    ParsedSymbol(_node_text(source, name_node), "module", _line(node), node.end_point[0] + 1)
                )
        for child in node.children:
            walk(child)

    walk(root)
    result.routes.extend(_extract_routes_from_text(text))
    return result


def parse_csharp(source: bytes, tree) -> ParseResult:
    result = ParseResult(line_count=source.count(b"\n") + 1)
    text = source.decode("utf-8", errors="replace")
    root = tree.root_node
    current_type: str | None = None

    def walk(node, parent_type: str | None = None):
        nonlocal current_type
        t = node.type
        if t in {
            "class_declaration",
            "interface_declaration",
            "struct_declaration",
            "enum_declaration",
            "record_declaration",
        }:
            name_node = node.child_by_field_name("name")
            if name_node:
                name = _node_text(source, name_node)
                kind = t.replace("_declaration", "")
                current_type = name
                result.symbols.append(ParsedSymbol(name, kind, _line(node), node.end_point[0] + 1))
        elif t in {"method_declaration", "constructor_declaration"}:
            name_node = node.child_by_field_name("name")
            if name_node:
                name = _node_text(source, name_node)
                params = node.child_by_field_name("parameters")
                sig = name + (_node_text(source, params) if params else "()")
                result.symbols.append(
                    ParsedSymbol(name, "method", _line(node), node.end_point[0] + 1, sig)
                )
                _extract_csharp_route_attributes(source, node, name, result)
        elif t == "property_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                result.symbols.append(
                    ParsedSymbol(_node_text(source, name_node), "property", _line(node), node.end_point[0] + 1)
                )
        elif t == "using_directive":
            result.imports.append(ParsedImport(_node_text(source, node).strip(), line=_line(node)))
        elif t == "namespace_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                result.symbols.append(
                    ParsedSymbol(_node_text(source, name_node), "namespace", _line(node), node.end_point[0] + 1)
                )
        for child in node.children:
            walk(child, current_type)

    walk(root)
    result.routes.extend(_extract_routes_from_text(text))
    result.routes.extend(_extract_csharp_minimal_apis(text))
    return result


def _extract_csharp_route_attributes(source: bytes, method_node, handler: str, result: ParseResult) -> None:
    parent = method_node.parent
    if not parent or parent.type != "attribute_list":
        return
    for child in parent.children:
        if child.type != "attribute":
            continue
        attr_text = _node_text(source, child)
        for pat, default_method in [
            (r'\[Http(Get|Post|Put|Delete|Patch)(?:\("([^"]+)"\))?\]', None),
            (r'\[Route\("([^"]+)"\)\]', "GET"),
        ]:
            m = re.search(pat, attr_text, re.IGNORECASE)
            if m:
                groups = m.groups()
                if len(groups) == 2 and groups[0] and groups[1] is not None:
                    method = groups[0].upper()
                    path = groups[1] or "/"
                elif len(groups) >= 1:
                    method = (default_method or "GET").upper()
                    path = groups[-1] or "/"
                else:
                    continue
                result.routes.append(
                    ParsedRoute(method, path, handler=handler, line=_line(method_node))
                )


def _extract_csharp_minimal_apis(text: str) -> list[ParsedRoute]:
    routes: list[ParsedRoute] = []
    patterns = [
        (r'\.Map(Get|Post|Put|Delete|Patch)\s*\(\s*"([^"]+)"', None),
        (r'app\.Map(Get|Post|Put|Delete|Patch)\s*\(\s*"([^"]+)"', None),
    ]
    for i, line in enumerate(text.splitlines(), start=1):
        for pat, _ in patterns:
            m = re.search(pat, line, re.IGNORECASE)
            if m:
                routes.append(ParsedRoute(m.group(1).upper(), m.group(2), line=i))
    return routes


def parse_dart(source: bytes, tree) -> ParseResult:
    result = ParseResult(line_count=source.count(b"\n") + 1)
    text = source.decode("utf-8", errors="replace")
    root = tree.root_node

    def walk(node):
        t = node.type
        if t == "class_definition":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = _node_text(source, name_node)
                kind = "widget" if name.endswith("Widget") or "State" in name else "class"
                result.symbols.append(ParsedSymbol(name, kind, _line(node), node.end_point[0] + 1))
        elif t in {"function_signature", "method_signature"}:
            name_node = node.child_by_field_name("name")
            if name_node:
                result.symbols.append(
                    ParsedSymbol(_node_text(source, name_node), "function", _line(node), node.end_point[0] + 1)
                )
        elif t == "import_specification":
            result.imports.append(ParsedImport(_node_text(source, node).strip(), line=_line(node)))
        for child in node.children:
            walk(child)

    walk(root)
    result.routes.extend(_extract_routes_from_text(text))
    return result


def parse_dockerfile(source: bytes, tree) -> ParseResult:
    result = ParseResult(line_count=source.count(b"\n") + 1)
    text = source.decode("utf-8", errors="replace")
    for i, line in enumerate(text.splitlines(), start=1):
        upper = line.strip().upper()
        if upper.startswith("FROM "):
            image = line.strip()[5:].split()[0]
            result.symbols.append(ParsedSymbol(image, "base_image", i, i, f"FROM {image}"))
        if upper.startswith("EXPOSE "):
            for port in line.strip()[7:].split():
                result.symbols.append(ParsedSymbol(port.split("/")[0], "port", i, i))
    return result


def regex_fallback(path: Path, content: str) -> ParseResult:
    result = ParseResult(line_count=content.count("\n") + 1)
    patterns = [
        (r"^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)", "function"),
        (r"^\s*(?:export\s+)?(?:default\s+)?class\s+(\w+)", "class"),
        (r"^\s*def\s+(\w+)\s*\(", "function"),
        (r"^\s*interface\s+(\w+)", "interface"),
        (r"^\s*public\s+class\s+(\w+)", "class"),
        (r"^\s*public\s+(?:async\s+)?(?:\w+\s+)?(\w+)\s*\(", "method"),
        (r"^\s*(?:pub\s+)?fn\s+(\w+)", "function"),
        (r"^\s*(?:pub\s+)?struct\s+(\w+)", "struct"),
        (r"^\s*class\s+(\w+)", "class"),
    ]
    for i, line in enumerate(content.splitlines(), start=1):
        for pattern, kind in patterns:
            m = re.match(pattern, line)
            if m:
                name = m.group(1)
                if kind == "function" and _is_component_name(name):
                    kind = "component"
                result.symbols.append(ParsedSymbol(name, kind, i, i))
        for imp_pat in [
            r"^\s*import\s+.+from\s+['\"]([^'\"]+)['\"]",
            r"^\s*from\s+(\S+)\s+import",
            r"^\s*import\s+([\w.]+)",
            r"^\s*using\s+([\w.]+)",
            r"^\s*use\s+([\w:]+)",
        ]:
            m = re.match(imp_pat, line)
            if m:
                result.imports.append(ParsedImport(m.group(1), line=i))
    result.routes.extend(_extract_routes_from_text(content))
    return result


def parse_file(path: Path) -> ParseResult:
    language = detect_language(path)
    if not language:
        return ParseResult()

    try:
        source = path.read_bytes()
    except OSError:
        return ParseResult()

    if not source:
        return ParseResult()

    # Dockerfile parsing is line-based; works without tree-sitter-dockerfile (e.g. on Windows)
    if language == "dockerfile":
        return parse_dockerfile(source, None)

    parser = _lang_parser(language)
    if parser:
        try:
            tree = parser.parse(source)
            dispatch = {
                "python": lambda: parse_python(source, tree),
                "javascript": lambda: parse_js_ts(source, tree, path.suffix.lower() == ".jsx"),
                "typescript": lambda: parse_js_ts(source, tree, path.suffix.lower() == ".tsx"),
                "go": lambda: parse_go(source, tree),
                "java": lambda: parse_java(source, tree),
                "rust": lambda: parse_rust(source, tree),
                "csharp": lambda: parse_csharp(source, tree),
                "dart": lambda: parse_dart(source, tree),
                "dockerfile": lambda: parse_dockerfile(source, tree),
            }
            fn = dispatch.get(language)
            if fn:
                return fn()
        except Exception:
            pass

    try:
        return regex_fallback(path, source.decode("utf-8", errors="replace"))
    except Exception:
        return ParseResult()
