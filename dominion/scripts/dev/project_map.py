#!/usr/bin/env python3
"""
project_mapper.py - Maps out Python project structure, dependencies, and module relationships.

Usage:
    python map.py <project_dir> [--depth N] [--output FILE]

Examples:
    python map.py .
    python map.py . --output map.txt
"""

import os
import sys
import ast
import argparse
from pathlib import Path
from collections import defaultdict

# ── ANSI colors ──────────────────────────────────────────────────────────────
C_RESET  = "\033[0m"
C_DIR    = "\033[1;34m"    # bold blue
C_PY     = "\033[1;33m"    # bold yellow
C_OTHER  = "\033[0;37m"    # gray
C_IMPORT = "\033[0;36m"    # cyan
C_HEADER = "\033[1;35m"    # bold magenta
C_DIM    = "\033[2m"
C_BOLD   = "\033[1m"
C_GREEN  = "\033[1;32m"
C_RED    = "\033[1;31m"
C_WARN   = "\033[1;33m"

# ── Defaults ─────────────────────────────────────────────────────────────────
DEFAULT_IGNORE = {
    "__pycache__", ".git", ".venv", "venv", "env", ".env",
    "node_modules", ".mypy_cache", ".pytest_cache", ".tox",
    "dist", "build", "*.egg-info", ".eggs", ".idea", ".vscode",
    ".pytest_cache", ".coverage", "htmlcov", ".hypothesis",
    "*.pyc", ".DS_Store", "Thumbs.db",
}

PY_EXTENSIONS = {".py", ".pyx", ".pyi"}


def parse_args():
    p = argparse.ArgumentParser(description="Map out Python project structure and dependencies.")
    p.add_argument("project_dir", help="Root directory of the project")
    p.add_argument("--depth", type=int, default=8, help="Max directory depth to display (default: 8)")
    p.add_argument("--output", type=str, default=None, help="Write plain-text output to file")
    p.add_argument("--ignore", type=str, default="", help="Comma-separated dirs to ignore")
    return p.parse_args()


# ── Import extraction ────────────────────────────────────────────────────────

def extract_imports(filepath: Path) -> tuple[list[str], list[str]]:
    """Parse AST and return (all_imports, relative_imports)."""
    try:
        source = filepath.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(source, filename=str(filepath))
    except (SyntaxError, ValueError, UnicodeDecodeError):
        return [], []

    imports = []
    relative = []
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            level = node.level
            if level > 0:
                relative.append((module, level))
            elif module:
                imports.append(module)
    
    return imports, relative


def extract_ast_details(filepath: Path) -> dict:
    """Extract classes, functions, async functions, and constants."""
    try:
        source = filepath.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(source, filename=str(filepath))
    except (SyntaxError, ValueError, UnicodeDecodeError):
        return {"classes": [], "functions": [], "async_functions": [], "constants": []}

    classes = []
    funcs = []
    async_funcs = []
    constants = []
    
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            classes.append(node.name)
        elif isinstance(node, ast.FunctionDef):
            if not node.name.startswith("_"):
                funcs.append(node.name)
        elif isinstance(node, ast.AsyncFunctionDef):
            if not node.name.startswith("_"):
                async_funcs.append(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    constants.append(target.id)
    
    return {
        "classes": classes,
        "functions": funcs,
        "async_functions": async_funcs,
        "constants": constants,
    }


def count_lines(filepath: Path) -> int:
    try:
        with filepath.open(encoding="utf-8", errors="ignore") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


# ── Tree rendering ───────────────────────────────────────────────────────────

def should_ignore(name: str, ignore_set: set[str]) -> bool:
    if name in ignore_set:
        return True
    for pattern in ignore_set:
        if pattern.startswith("*") and name.endswith(pattern[1:]):
            return True
    return False


def render_tree(
    root: Path,
    ignore_set: set[str],
    max_depth: int,
    lines_out: list[str],
    py_files: list[Path],
    prefix: str = "",
    depth: int = 0,
):
    """Recursively render directory tree."""
    if depth > max_depth:
        return

    try:
        entries = sorted(root.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
    except PermissionError:
        return

    dirs = [e for e in entries if e.is_dir() and not should_ignore(e.name, ignore_set)]
    files = [e for e in entries if e.is_file() and not should_ignore(e.name, ignore_set)]

    items = dirs + files
    for i, entry in enumerate(items):
        is_last = (i == len(items) - 1)
        connector = "└── " if is_last else "├── "
        extension = "    " if is_last else "│   "

        if entry.is_dir():
            py_count = sum(1 for _ in entry.rglob("*.py"))
            label = f"{C_DIR}{entry.name}/{C_RESET}"
            if py_count:
                label += f"  {C_DIM}({py_count} .py){C_RESET}"
            lines_out.append(f"{prefix}{connector}{label}")
            render_tree(entry, ignore_set, max_depth, lines_out, py_files, prefix + extension, depth + 1)
        else:
            suffix = entry.suffix
            lc = count_lines(entry)
            lc_str = f"  {C_DIM}({lc}L){C_RESET}" if lc else ""

            if suffix in PY_EXTENSIONS:
                py_files.append(entry)
                details = extract_ast_details(entry)
                
                detail_parts = []
                if details["classes"]:
                    detail_parts.append(f"C:{len(details['classes'])}")
                if details["functions"]:
                    detail_parts.append(f"F:{len(details['functions'])}")
                if details["async_functions"]:
                    detail_parts.append(f"AF:{len(details['async_functions'])}")
                
                detail = ""
                if detail_parts:
                    detail = f"  {C_DIM}[{' | '.join(detail_parts)}]{C_RESET}"

                lines_out.append(f"{prefix}{connector}{C_PY}{entry.name}{C_RESET}{lc_str}{detail}")
            else:
                lines_out.append(f"{prefix}{connector}{C_OTHER}{entry.name}{C_RESET}{lc_str}")


# ── Dependency analysis ──────────────────────────────────────────────────────

def build_full_import_map(py_files: list[Path], root: Path) -> dict:
    """Build comprehensive import map with internal/external classification."""
    internal_modules = set()
    
    for f in py_files:
        try:
            rel = f.relative_to(root).with_suffix("")
            parts = rel.parts
            internal_modules.add(".".join(parts))
            for i in range(1, len(parts)):
                internal_modules.add(".".join(parts[:i]))
        except ValueError:
            continue

    import_map = {}
    for f in py_files:
        try:
            rel = str(f.relative_to(root))
            imports, relative_imports = extract_imports(f)
            
            internal = []
            external = []
            
            for imp in imports:
                top_level = imp.split(".")[0]
                if top_level in internal_modules or imp in internal_modules:
                    internal.append(imp)
                else:
                    external.append(imp)
            
            import_map[rel] = {
                "internal": sorted(set(internal)),
                "external": sorted(set(external)),
                "relative": relative_imports,
            }
        except ValueError:
            continue
    
    return import_map


def detect_circular_imports(import_map: dict) -> list[tuple[str, str]]:
    """Simple heuristic to detect potential circular imports."""
    reverse = defaultdict(set)
    for source, data in import_map.items():
        for target in data["internal"]:
            reverse[target].add(source)
    
    cycles = []
    for source, data in import_map.items():
        for target in data["internal"]:
            if source in reverse.get(target, set()):
                pair = tuple(sorted([source, target]))
                if pair not in cycles:
                    cycles.append(pair)
    
    return cycles


def external_deps_ranked(import_map: dict) -> list[tuple[str, int]]:
    """Count usage of each external package."""
    counter = defaultdict(int)
    for data in import_map.values():
        for imp in data["external"]:
            top = imp.split(".")[0]
            counter[top] += 1
    return sorted(counter.items(), key=lambda x: -x[1])


def module_depth_analysis(import_map: dict) -> dict:
    """Analyze import depth and clustering."""
    depth_map = defaultdict(int)
    for fpath in import_map.keys():
        depth = len(Path(fpath).parts)
        depth_map[depth] += 1
    
    return dict(sorted(depth_map.items()))


# ── Stats ────────────────────────────────────────────────────────────────────

def compute_stats(py_files: list[Path]) -> dict:
    """Compute codebase statistics."""
    total_lines = 0
    total_classes = 0
    total_funcs = 0
    total_async = 0
    biggest = ("", 0)
    largest_class_count = ("", 0)

    for f in py_files:
        lc = count_lines(f)
        total_lines += lc
        if lc > biggest[1]:
            biggest = (f.name, lc)
        
        details = extract_ast_details(f)
        total_classes += len(details["classes"])
        total_funcs += len(details["functions"])
        total_async += len(details["async_functions"])
        
        if len(details["classes"]) > largest_class_count[1]:
            largest_class_count = (f.name, len(details["classes"]))

    avg_lines = total_lines // len(py_files) if py_files else 0
    
    return {
        "files": len(py_files),
        "lines": total_lines,
        "avg_lines_per_file": avg_lines,
        "classes": total_classes,
        "functions": total_funcs,
        "async_functions": total_async,
        "biggest_file": biggest,
        "class_dense_file": largest_class_count,
    }


# ── Detect key files ─────────────────────────────────────────────────────────

def detect_entry_points(py_files: list[Path], root: Path) -> dict:
    """Detect main entry points, CLI, tests, configs."""
    categories = {
        "main": [],
        "cli": [],
        "tests": [],
        "config": [],
        "utils": [],
    }
    
    for f in py_files:
        try:
            rel_path = f.relative_to(root)
            name = f.name.lower()
            parts = rel_path.parts
            
            if name in ["__main__.py", "main.py", "run.py", "start.py"]:
                categories["main"].append(str(rel_path))
            elif any(x in name for x in ["cli", "command", "cmd", "argparse"]):
                categories["cli"].append(str(rel_path))
            elif "test" in name or any("test" in p for p in parts):
                categories["tests"].append(str(rel_path))
            elif any(x in name for x in ["config", "settings", "conf"]):
                categories["config"].append(str(rel_path))
            elif any(x in name for x in ["util", "helper", "common"]):
                categories["utils"].append(str(rel_path))
        except ValueError:
            continue
    
    return {k: v for k, v in categories.items() if v}


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()
    root = Path(args.project_dir).resolve()

    if not root.is_dir():
        print(f"{C_RED}Error:{C_RESET} '{root}' is not a directory.")
        sys.exit(1)

    ignore_set = set(DEFAULT_IGNORE)
    if args.ignore:
        ignore_set.update(i.strip() for i in args.ignore.split(","))

    output = []
    
    # ── HEADER ───────────────────────────────────────────────────────────
    output.append(f"\n{C_HEADER}{'═' * 80}{C_RESET}")
    output.append(f"{C_HEADER}  PROJECT MAP: {root.name}{C_RESET}")
    output.append(f"{C_HEADER}{'═' * 80}{C_RESET}\n")

    # ── STRUCTURE ────────────────────────────────────────────────────────
    output.append(f"{C_BOLD}DIRECTORY STRUCTURE{C_RESET}")
    output.append(f"{C_DIR}{root.name}/{C_RESET}")
    
    py_files: list[Path] = []
    render_tree(root, ignore_set, args.depth, output, py_files)
    output.append("")

    # ── STATS ────────────────────────────────────────────────────────────
    stats = compute_stats(py_files)
    output.append(f"{C_BOLD}CODEBASE STATISTICS{C_RESET}")
    output.append(f"   Python files         : {C_GREEN}{stats['files']}{C_RESET}")
    output.append(f"   Total lines          : {C_GREEN}{stats['lines']:,}{C_RESET}")
    output.append(f"   Avg lines/file       : {stats['avg_lines_per_file']}")
    output.append(f"   Total classes        : {C_GREEN}{stats['classes']}{C_RESET}")
    output.append(f"   Total functions      : {C_GREEN}{stats['functions']}{C_RESET}")
    output.append(f"   Async functions      : {stats['async_functions']}")
    if stats["biggest_file"][1]:
        output.append(f"   Biggest file         : {C_PY}{stats['biggest_file'][0]}{C_RESET} ({stats['biggest_file'][1]:,}L)")
    if stats["class_dense_file"][1]:
        output.append(f"   Most class-dense     : {C_PY}{stats['class_dense_file'][0]}{C_RESET} ({stats['class_dense_file'][1]} classes)")
    output.append("")

    # ── ENTRY POINTS ─────────────────────────────────────────────────────
    entry_points = detect_entry_points(py_files, root)
    if entry_points:
        output.append(f"{C_BOLD}KEY ENTRY POINTS & CATEGORIZED FILES{C_RESET}")
        for category, files in entry_points.items():
            output.append(f"   {C_IMPORT}{category.upper()}{C_RESET}")
            for f in files[:10]:
                output.append(f"      - {f}")
            if len(files) > 10:
                output.append(f"      ... and {len(files) - 10} more")
        output.append("")

    # ── DEPENDENCY ANALYSIS ──────────────────────────────────────────────
    if py_files:
        import_map = build_full_import_map(py_files, root)
        
        # External dependencies
        ext_deps = external_deps_ranked(import_map)
        if ext_deps:
            output.append(f"{C_BOLD}EXTERNAL DEPENDENCIES{C_RESET}  (ranked by usage)")
            for pkg, count in ext_deps[:30]:
                bar_width = min(count * 2, 50)
                bar = "█" * bar_width
                output.append(f"   {C_IMPORT}{pkg:<30}{C_RESET} {bar} ({count})")
            output.append("")
        
        # Internal wiring
        has_internal = any(d["internal"] for d in import_map.values())
        if has_internal:
            output.append(f"{C_BOLD}INTERNAL MODULE DEPENDENCIES{C_RESET}")
            internal_count = 0
            for fpath, data in sorted(import_map.items()):
                if data["internal"] and internal_count < 40:
                    targets = ", ".join(data["internal"][:5])
                    if len(data["internal"]) > 5:
                        targets += f", ... +{len(data['internal']) - 5}"
                    output.append(f"   {C_PY}{fpath}{C_RESET}")
                    output.append(f"      -> {C_IMPORT}{targets}{C_RESET}")
                    internal_count += 1
            
            if has_internal and internal_count >= 40:
                total_internal_edges = sum(len(d["internal"]) for d in import_map.values())
                output.append(f"   ... and {total_internal_edges - (internal_count * 5)} more internal imports")
            output.append("")
        
        # Circular imports
        cycles = detect_circular_imports(import_map)
        if cycles:
            output.append(f"{C_WARN}POTENTIAL CIRCULAR IMPORTS{C_RESET}")
            for a, b in cycles[:10]:
                output.append(f"   {C_RED}{a}{C_RESET} <-> {C_RED}{b}{C_RESET}")
            if len(cycles) > 10:
                output.append(f"   ... and {len(cycles) - 10} more potential cycles")
            output.append("")
        
        # Module depth
        depth_dist = module_depth_analysis(import_map)
        if depth_dist:
            output.append(f"{C_BOLD}MODULE NESTING DEPTH{C_RESET}")
            for depth, count in depth_dist.items():
                bar = "▓" * min(count, 40)
                output.append(f"   Depth {depth}: {bar} {count} files")
            output.append("")

    # ── Config files ─────────────────────────────────────────────────────
    config_files = []
    for name in ["setup.py", "setup.cfg", "pyproject.toml", "Makefile", "Dockerfile",
                  "docker-compose.yml", "requirements.txt", "requirements-dev.txt",
                  "Pipfile", "poetry.lock", "tox.ini", ".pre-commit-config.yaml",
                  "README.md", "LICENSE", ".gitignore", "pytest.ini", "conftest.py"]:
        if (root / name).exists():
            config_files.append(name)
    
    if config_files:
        output.append(f"{C_BOLD}PROJECT CONFIGURATION FILES{C_RESET}")
        for f in config_files:
            output.append(f"   {f}")
        output.append("")

    output.append(f"{C_HEADER}{'═' * 80}{C_RESET}\n")

    # ── PRINT & SAVE ─────────────────────────────────────────────────────
    full = "\n".join(output)
    print(full)

    if args.output:
        import re
        clean = re.sub(r"\033\[[0-9;]*m", "", full)
        Path(args.output).write_text(clean, encoding="utf-8")
        print(f"{C_GREEN}Saved to {args.output}{C_RESET}\n")


if __name__ == "__main__":
    main()