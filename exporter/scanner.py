"""Discover PHP source files in a file or directory target."""

from pathlib import Path
from typing import List, Tuple

PHP_EXTENSIONS = {".php", ".inc", ".phar"}


def scan(target: str) -> Tuple[List[str], str]:
    """
    Return (sorted list of absolute file paths, project root).
    If target is a file, root is its parent directory.
    If target is a directory, root is that directory.
    """
    p = Path(target).resolve()
    if p.is_file():
        return [str(p)], str(p.parent)
    files = sorted(
        str(f.resolve())
        for ext in PHP_EXTENSIONS
        for f in p.rglob(f"*{ext}")
    )
    return files, str(p)
