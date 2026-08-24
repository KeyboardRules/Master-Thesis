#!/usr/bin/env python
"""
Semantic-preserving PHP perturbation harness (Phase-3, robustness §2).

Produces transformed copies of a PHP file that must NOT change the vulnerability, so a robust
detector should keep its verdict. Robustness flow:
    vuln/ PHP  --perturb-->  rebuild E-CPG  -->  slice (backward_slice)  -->  linearize  -->  infer
then compare the verdict on original vs perturbed (consistency).

Transforms (all best-effort, regex-based; each is designed to preserve taint semantics):
  rename_variables       consistent $var -> $vN   (skips superglobals, $this)
  insert_dead_code       unused benign assignments after <?php and after `function ... {`
  insert_comments        // comment lines interleaved
  change_formatting      extra blank lines / indentation noise
  reorder_assignments    swap two ADJACENT literal assignments (independent)
  add_include_indirection prepend a require of a generated no-op wrapper (stresses the MDG step)

CLI:
  python perturb.py <in.php> --out-dir out/ [--transforms rename_variables,insert_dead_code]
  python perturb.py --sample dataset_xmodule/CWE-78/GHSA-xxxx --out-dir out/   # perturb its vuln/ files

Writes one file per (input, transform) plus manifest.jsonl {orig, transform, output, seed}.
NOTE: rename is naive whole-file — safe for single-scope slices; flag multi-scope files.
"""
import argparse, json, os, random, re
from pathlib import Path

_SUPERGLOBAL = re.compile(r"\$_(?:GET|POST|REQUEST|COOKIE|FILES|SERVER|ENV|SESSION)\b")
_VAR = re.compile(r"\$[A-Za-z_]\w*")
_PHP_OPEN = re.compile(r"<\?php")
_FUNC_OPEN = re.compile(r"(function\s+\w+\s*\([^)]*\)\s*(?::\s*\??\w+\s*)?\{)")


def rename_variables(src: str, rng: random.Random) -> str:
    keep = {"$this"}
    names = []
    for m in _VAR.finditer(src):
        v = m.group(0)
        if v in keep or _SUPERGLOBAL.match(v):
            continue
        if v not in names:
            names.append(v)
    mapping = {v: f"$v{i}" for i, v in enumerate(names, 1)}
    # replace longest names first to avoid prefix collisions
    for v in sorted(mapping, key=len, reverse=True):
        src = re.sub(re.escape(v) + r"\b", mapping[v].replace("\\", "\\\\"), src)
    return src


def insert_dead_code(src: str, rng: random.Random) -> str:
    dead = f"$__dead{rng.randint(1000,9999)} = {rng.randint(0,999)}; // perturb"
    src = _PHP_OPEN.sub(lambda m: m.group(0) + "\n" + dead, src, count=1)
    src = _FUNC_OPEN.sub(lambda m: m.group(1) + "\n    " + dead + "\n", src, count=2)
    return src


def insert_comments(src: str, rng: random.Random) -> str:
    out = []
    for i, line in enumerate(src.splitlines()):
        out.append(line)
        if line.strip().endswith(";") and rng.random() < 0.25:
            out.append("// note " + str(rng.randint(0, 9999)))
    return "\n".join(out)


def change_formatting(src: str, rng: random.Random) -> str:
    out = []
    for line in src.splitlines():
        out.append(line)
        if line.strip().endswith("{") or (line.strip().endswith(";") and rng.random() < 0.3):
            out.append("")                     # extra blank line
    return "\n".join(out)


def reorder_assignments(src: str, rng: random.Random) -> str:
    """Swap two ADJACENT simple literal assignments `$a = <literal>;` (independent)."""
    lines = src.splitlines()
    lit = re.compile(r"^\s*\$\w+\s*=\s*['\"]?[\w./-]+['\"]?\s*;\s*$")
    for i in range(len(lines) - 1):
        if lit.match(lines[i]) and lit.match(lines[i + 1]):
            lva = lines[i].split("=")[0].strip()
            if lva not in lines[i + 1]:        # 2nd stmt does not use the 1st's lhs -> independent
                lines[i], lines[i + 1] = lines[i + 1], lines[i]
                break
    return "\n".join(lines)


def add_include_indirection(src: str, rng: random.Random) -> str:
    """Prepend a require of a no-op wrapper -> adds an INCLUDE edge the analysis must cross."""
    wrapper = f"__perturb_noop_{rng.randint(1000,9999)}.php"
    stub = f"require_once __DIR__ . '/{wrapper}';   // perturb: extra include layer"
    return _PHP_OPEN.sub(lambda m: m.group(0) + "\n" + stub, src, count=1)


TRANSFORMS = {
    "rename_variables": rename_variables,
    "insert_dead_code": insert_dead_code,
    "insert_comments": insert_comments,
    "change_formatting": change_formatting,
    "reorder_assignments": reorder_assignments,
    "add_include_indirection": add_include_indirection,
}


def perturb_file(in_path: str, out_dir: str, transforms, seed: int, manifest):
    src = Path(in_path).read_text(encoding="utf-8", errors="replace")
    base = Path(in_path).stem
    for name in transforms:
        rng = random.Random(seed)
        out = TRANSFORMS[name](src, rng)
        op = os.path.join(out_dir, f"{base}.{name}.php")
        Path(op).write_text(out, encoding="utf-8")
        manifest.write(json.dumps({"orig": in_path, "transform": name, "output": op, "seed": seed}) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", nargs="?", help="a .php file")
    ap.add_argument("--sample", help="a dataset_xmodule/<CWE>/<id> dir; perturb its vuln/*.php")
    ap.add_argument("--out-dir", default="perturbed")
    ap.add_argument("--transforms", default=",".join(TRANSFORMS))
    ap.add_argument("--seed", type=int, default=13)
    args = ap.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)
    transforms = [t for t in args.transforms.split(",") if t in TRANSFORMS]

    inputs = []
    if args.sample:
        inputs = [str(p) for p in Path(args.sample, "vuln").glob("*.php")]
    elif args.input:
        inputs = [args.input]
    else:
        ap.error("give a .php file or --sample <dir>")

    with open(os.path.join(args.out_dir, "manifest.jsonl"), "w", encoding="utf-8") as man:
        for f in inputs:
            perturb_file(f, args.out_dir, transforms, args.seed, man)
    print(f"perturbed {len(inputs)} file(s) x {len(transforms)} transform(s) -> {args.out_dir}")


if __name__ == "__main__":
    main()
