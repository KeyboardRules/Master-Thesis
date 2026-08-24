"""
Regex-based PHP source parser.

Extracts three categories of information per file:
  1. Scalar string constants  (define() and const)
  2. Include / require statements, with best-effort path resolution
  3. Class / interface / trait declarations, including inheritance and trait use

Known limitations (acceptable for MVP):
  - Heredoc/nowdoc strings containing // or /* may interfere with comment stripping.
  - String literals containing { or } can confuse brace-count-based body extraction.
  - Fully-qualified trait names (e.g. `use Ns\\MyTrait`) are excluded from USE_TRAIT
    edges because the CHG uses simple names as node IDs.
  - Dynamic include paths that cannot be resolved from static constants are recorded
    as 'unresolved'.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


# ──────────────────────────────────────────────────────────────────────────────
# Data structures
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class IncludeStmt:
    stmt_type: str           # include | require | include_once | require_once
    raw_expr: str            # verbatim expression from source
    resolved: Optional[str]  # absolute path when successfully resolved, else None
    line: int


@dataclass
class ClassDecl:
    name: str
    kind: str                # class | abstract_class | interface | trait
    extends: List[str]       # PHP classes extend ≤1; interfaces may extend many
    implements: List[str]    # interfaces implemented by a class
    uses_traits: List[str]   # traits pulled in with `use Trait;`
    file: str
    line: int


@dataclass
class FileAnalysis:
    path: str
    constants: Dict[str, str] = field(default_factory=dict)
    includes: List[IncludeStmt] = field(default_factory=list)
    classes: List[ClassDecl] = field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────────────
# Comment stripping
# ──────────────────────────────────────────────────────────────────────────────

def _strip_comments(src: str) -> str:
    """
    Remove /* ... */ block comments and // / # line comments.
    Block-comment content is replaced with an equivalent number of newlines
    so that line numbers remain correct for error reporting.
    """
    def _block_sub(m: re.Match) -> str:
        return "\n" * m.group(0).count("\n")

    src = re.sub(r"/\*.*?\*/", _block_sub, src, flags=re.DOTALL)
    src = re.sub(r"(//|#)[^\n]*", "", src)
    return src


def _line_of(src: str, pos: int) -> int:
    """Return 1-based line number for byte offset pos in src."""
    return src[:pos].count("\n") + 1


# ──────────────────────────────────────────────────────────────────────────────
# Constant extraction
# ──────────────────────────────────────────────────────────────────────────────

# define("NAME", "value")
_DEFINE_RE = re.compile(
    r"""define\s*\(\s*['"](\w+)['"]\s*,\s*['"]([^'"]*)['"]\s*\)""",
    re.IGNORECASE,
)
# const NAME = "value";
_CONST_RE = re.compile(
    r"""\bconst\s+(\w+)\s*=\s*['"]([^'"]*)['"]\s*;""",
    re.MULTILINE,
)


def extract_constants(src: str) -> Dict[str, str]:
    """Extract scalar string constants defined via define() or const."""
    consts: Dict[str, str] = {}
    for m in _DEFINE_RE.finditer(src):
        consts[m.group(1)] = m.group(2)
    for m in _CONST_RE.finditer(src):
        consts[m.group(1)] = m.group(2)
    return consts


# ──────────────────────────────────────────────────────────────────────────────
# Include / require extraction
# ──────────────────────────────────────────────────────────────────────────────

# Capture everything between the keyword and the statement-ending semicolon.
# [^;]+ stops at the semicolon without needing lookaheads.
_INCLUDE_RE = re.compile(
    r"\b(include_once|require_once|include|require)\b\s*([^;]+?)\s*;",
    re.MULTILINE,
)


def _resolve_expr(expr: str, file_dir: str, consts: Dict[str, str]) -> Optional[str]:
    """
    Attempt to reduce `expr` to a concrete file-path string.

    Steps applied in order:
      1. Strip outer parentheses:  include("x") → "x"
      2. Substitute known constants
      3. Replace dirname(__FILE__) / __DIR__ with the file's directory
      4. Replace DIRECTORY_SEPARATOR with "/"
      5. Collect all quoted substrings and concatenate them
    """
    expr = expr.strip()

    # 1. Strip outer parens only when the inner part is balanced
    if expr.startswith("(") and expr.endswith(")"):
        inner = expr[1:-1].strip()
        if inner.count("(") == inner.count(")"):
            expr = inner

    # 2. Substitute known string constants
    for name, val in consts.items():
        expr = re.sub(r"\b" + re.escape(name) + r"\b", f'"{val}"', expr)

    # 3. Replace dirname(__FILE__) and __DIR__ with the containing directory
    safe_dir = file_dir.replace("\\", "/")
    expr = re.sub(
        r"dirname\s*\(\s*__FILE__\s*\)|__DIR__",
        f'"{safe_dir}"',
        expr,
        flags=re.IGNORECASE,
    )

    # 4. Normalize DIRECTORY_SEPARATOR
    expr = re.sub(r"\bDIRECTORY_SEPARATOR\b", '"/"', expr)

    # 5. Collect quoted segments and join
    parts = re.findall(r'"([^"]*)"', expr)
    if not parts:
        parts = re.findall(r"'([^']*)'", expr)
    if not parts:
        return None  # expression is too dynamic to resolve statically

    return "".join(parts)


def extract_includes(src: str, file_path: str, consts: Dict[str, str]) -> List[IncludeStmt]:
    file_dir = str(Path(file_path).parent).replace("\\", "/")
    stmts: List[IncludeStmt] = []

    for m in _INCLUDE_RE.finditer(src):
        stmt_type = m.group(1)
        raw_expr = m.group(2).strip()
        line = _line_of(src, m.start())

        rel = _resolve_expr(raw_expr, file_dir, consts)
        if rel is not None:
            # Resolve relative to the including file's directory
            resolved = str((Path(file_path).parent / rel).resolve())
        else:
            resolved = None

        stmts.append(IncludeStmt(
            stmt_type=stmt_type,
            raw_expr=raw_expr,
            resolved=resolved,
            line=line,
        ))
    return stmts


# ──────────────────────────────────────────────────────────────────────────────
# Class / interface / trait extraction
# ──────────────────────────────────────────────────────────────────────────────

# Matches the full class/interface/trait declaration header up to and including
# the opening '{'.  Uses named groups for clarity.
_CLASS_RE = re.compile(
    r"""
    (?:(?P<mod>abstract|final)\s+)?       # optional modifier
    (?P<kind>class|interface|trait)\s+    # declaration keyword
    (?P<name>\w+)                          # type name
    (?:\s+extends\s+
        (?P<extends>[\w\\]+               # first parent name
          (?:\s*,\s*[\w\\]+)*)            # additional parents (for interfaces)
    )?
    (?:\s+implements\s+
        (?P<implements>[\w\\]+            # first interface
          (?:\s*,\s*[\w\\]+)*)           # additional interfaces
    )?
    \s*\{                                 # opening brace — consumed by the match
    """,
    re.VERBOSE | re.MULTILINE,
)

# Matches trait-use statements inside a class body.
# Ends with ';' (simple use) or '{' (conflict-resolution block).
_TRAIT_USE_RE = re.compile(
    r"\buse\s+([\w\\]+(?:\s*,\s*[\w\\]+)*)\s*(?:;|\{)",
    re.MULTILINE,
)


def _extract_body(src: str, open_brace_pos: int) -> str:
    """
    Return the text between the brace at open_brace_pos and its matching
    closing brace, using a simple depth counter.

    Assumption: brace characters inside string literals or heredocs may cause
    an incorrect match (known MVP limitation).
    """
    assert src[open_brace_pos] == "{", (
        f"Expected '{{' at pos {open_brace_pos}, got {src[open_brace_pos]!r}"
    )
    depth = 1
    i = open_brace_pos + 1
    while i < len(src) and depth > 0:
        ch = src[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        i += 1
    return src[open_brace_pos + 1 : i - 1]


def _split_names(s: Optional[str]) -> List[str]:
    if not s:
        return []
    return [n.strip() for n in re.split(r"\s*,\s*", s.strip()) if n.strip()]


def extract_classes(src: str, file_path: str) -> List[ClassDecl]:
    decls: List[ClassDecl] = []

    for m in _CLASS_RE.finditer(src):
        mod = (m.group("mod") or "").lower()
        kind_raw = m.group("kind").lower()
        name = m.group("name")

        if kind_raw == "trait":
            kind = "trait"
        elif kind_raw == "interface":
            kind = "interface"
        elif mod == "abstract":
            kind = "abstract_class"
        else:
            kind = "class"

        extends = _split_names(m.group("extends"))
        implements = _split_names(m.group("implements"))

        # The regex consumes the '{', so m.end()-1 is its position in src.
        open_brace = m.end() - 1
        body = _extract_body(src, open_brace)

        # Trait-use statements are only meaningful inside class/abstract class bodies.
        uses_traits: List[str] = []
        if kind in ("class", "abstract_class"):
            for tm in _TRAIT_USE_RE.finditer(body):
                for t in _split_names(tm.group(1)):
                    # Exclude fully-qualified names (contain \) — simple names only
                    if "\\" not in t:
                        uses_traits.append(t)

        decls.append(ClassDecl(
            name=name,
            kind=kind,
            extends=extends,
            implements=implements,
            uses_traits=uses_traits,
            file=file_path,
            line=_line_of(src, m.start()),
        ))
    return decls


# ──────────────────────────────────────────────────────────────────────────────
# Public entry point
# ──────────────────────────────────────────────────────────────────────────────

def analyze_file(file_path: str) -> FileAnalysis:
    """Analyze a single PHP file and return all extracted declarations."""
    try:
        raw = Path(file_path).read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        print(f"[!] Cannot read {file_path}: {e}")
        return FileAnalysis(path=file_path)

    src = _strip_comments(raw)
    consts = extract_constants(src)
    includes = extract_includes(src, file_path, consts)
    classes = extract_classes(src, file_path)

    return FileAnalysis(
        path=file_path,
        constants=consts,
        includes=includes,
        classes=classes,
    )
