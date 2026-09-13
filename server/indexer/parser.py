import re
from dataclasses import dataclass, field
from pathlib import Path

from tree_sitter import Language, Parser
import tree_sitter_python
import tree_sitter_javascript
import tree_sitter_typescript
import tree_sitter_go

from server.indexer.walker import detect_language


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
    mapping = {
        "python": Language(tree_sitter_python.language()),
        "javascript": Language(tree_sitter_javascript.language()),
        "typescript": Language(tree_sitter_typescript.language_typescript()),
        "go": Language(tree_sitter_go.language()),
    }
    lang = mapping.get(language)
    if not lang:
        return None
    parser = Parser(lang)
    return parser


def _node_text(source: bytes, node) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _line(node) -> int:
    return node.start_point[0] + 1


def parse_python(source: bytes, tree) -> ParseResult:
    result = ParseResult(line_count=source.count(b"\n") + 1)
    root = tree.root_node

    def walk(node):
        if node.type == "function_definition":
            name_node = node.child_by_field_name("name")
            params = node.child_by_field_name("parameters")
            if name_node:
                name = _node_text(source, name_node)
                sig = name
                if params:
                    sig += _node_text(source, params)
                result.symbols.append(
                    ParsedSymbol(name, "function", _line(node), node.end_point[0] + 1, sig)
                )
        elif node.type == "class_definition":
            name_node = node.child_by_field_name("name")
            if name_node:
                result.symbols.append(
                    ParsedSymbol(
                        _node_text(source, name_node),
                        "class",
                        _line(node),
                        node.end_point[0] + 1,
                    )
                )
        elif node.type == "import_statement":
            text = _node_text(source, node).strip()
            m = re.match(r"import\s+([\w.]+)", text)
            result.imports.append(
                ParsedImport(m.group(1) if m else text, line=_line(node))
            )
        elif node.type == "import_from_statement":
            module = node.child_by_field_name("module_name")
            if module:
                result.imports.append(
                    ParsedImport(_node_text(source, module), line=_line(node))
                )
        elif node.type == "decorated_definition":
            for child in node.children:
                if child.type == "decorator":
                    text = _node_text(source, child)
                    for pattern in [
                        r'@app\.(get|post|put|delete|patch)\(["\']([^"\']+)["\']',
                        r'@router\.(get|post|put|delete|patch)\(["\']([^"\']+)["\']',
                        r'@api_view\(\[["\'](\w+)["\']',
                    ]:
                        m = re.search(pattern, text)
                        if m:
                            if "api_view" in pattern:
                                result.routes.append(
                                    ParsedRoute(m.group(1).upper(), "/*", line=_line(child))
                                )
                            else:
                                result.routes.append(
                                    ParsedRoute(m.group(1).upper(), m.group(2), line=_line(child))
                                )
        for child in node.children:
            walk(child)

    walk(root)
    return result


def parse_js_ts(source: bytes, tree) -> ParseResult:
    result = ParseResult(line_count=source.count(b"\n") + 1)
    root = tree.root_node

    def walk(node):
        t = node.type
        if t in {"function_declaration", "method_definition", "arrow_function"}:
            name_node = node.child_by_field_name("name")
            if name_node:
                result.symbols.append(
                    ParsedSymbol(
                        _node_text(source, name_node),
                        "function" if t != "method_definition" else "method",
                        _line(node),
                        node.end_point[0] + 1,
                    )
                )
        elif t == "class_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                result.symbols.append(
                    ParsedSymbol(
                        _node_text(source, name_node),
                        "class",
                        _line(node),
                        node.end_point[0] + 1,
                    )
                )
        elif t == "interface_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                result.symbols.append(
                    ParsedSymbol(
                        _node_text(source, name_node),
                        "interface",
                        _line(node),
                        node.end_point[0] + 1,
                    )
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
                for method in ["get", "post", "put", "delete", "patch"]:
                    if f".{method}(" in fn_text or fn_text == method:
                        m = re.search(r'["\']([^"\']+)["\']', args_text)
                        if m:
                            result.routes.append(
                                ParsedRoute(method.upper(), m.group(1), line=_line(node))
                            )
        for child in node.children:
            walk(child)

    walk(root)
    return result


def parse_go(source: bytes, tree) -> ParseResult:
    result = ParseResult(line_count=source.count(b"\n") + 1)
    root = tree.root_node

    def walk(node):
        if node.type == "function_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                result.symbols.append(
                    ParsedSymbol(
                        _node_text(source, name_node),
                        "function",
                        _line(node),
                        node.end_point[0] + 1,
                    )
                )
        elif node.type == "type_declaration":
            for child in node.children:
                if child.type == "type_spec":
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        result.symbols.append(
                            ParsedSymbol(
                                _node_text(source, name_node),
                                "type",
                                _line(child),
                                child.end_point[0] + 1,
                            )
                        )
        elif node.type == "import_declaration":
            result.imports.append(ParsedImport(_node_text(source, node).strip(), line=_line(node)))
        for child in node.children:
            walk(child)

    walk(root)
    return result


def regex_fallback(path: Path, content: str) -> ParseResult:
    result = ParseResult(line_count=content.count("\n") + 1)
    patterns = [
        (r"^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)", "function"),
        (r"^\s*class\s+(\w+)", "class"),
        (r"^\s*def\s+(\w+)\s*\(", "function"),
        (r"^\s*interface\s+(\w+)", "interface"),
    ]
    for i, line in enumerate(content.splitlines(), start=1):
        for pattern, kind in patterns:
            m = re.match(pattern, line)
            if m:
                result.symbols.append(ParsedSymbol(m.group(1), kind, i, i))
        imp = re.match(r"^\s*import\s+.+from\s+['\"]([^'\"]+)['\"]", line)
        if imp:
            result.imports.append(ParsedImport(imp.group(1), line=i))
        imp_py = re.match(r"^\s*from\s+(\S+)\s+import", line)
        if imp_py:
            result.imports.append(ParsedImport(imp_py.group(1), line=i))
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

    parser = _lang_parser(language)
    if parser:
        try:
            tree = parser.parse(source)
            if language == "python":
                return parse_python(source, tree)
            if language in {"javascript", "typescript"}:
                return parse_js_ts(source, tree)
            if language == "go":
                return parse_go(source, tree)
        except Exception:
            pass

    try:
        return regex_fallback(path, source.decode("utf-8", errors="replace"))
    except Exception:
        return ParseResult()
