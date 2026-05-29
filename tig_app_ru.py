#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TIG Unified v1.3 (Canon & Studio Edition)
Инструмент для управления эволюцией кода, намерениями и контекстом AI.
"""

import os
import sys
import time
import threading
import re
import json
import hashlib
import argparse
from datetime import datetime
from pathlib import Path
import subprocess
from typing import Any, Dict, List, Optional, Set, Tuple
from collections import defaultdict

# ============================================================================
# КОНСТАНТЫ И НАСТРОЙКИ
# ============================================================================
MAX_FILE_SIZE_MB = 10
MAX_FILE_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024

EXCLUDE_EXTENSIONS = {
    '.exe', '.dll', '.so', '.dylib', '.bin', '.tig',
    '.o', '.obj', '.pyc', '.pyo', '.pyd', 
    '.class', '.jar', '.war', '.ear', '.pdb',
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg',
    '.mp3', '.mp4', '.avi', '.mov', '.wav', '.flac',
    '.zip', '.tar', '.gz', '.rar', '.7z', '.bz2', '.xz',
    '.db', '.sqlite', '.sqlite3', '.cache', '.log', '.tmp', '.temp', '.swp', '.swo',
    '.suo', '.user', '.csproj', '.sln',
    '.xcodeproj', '.xcworkspace', '.iml', '.pt'
}

EXCLUDE_DIRS = {
    '.git', '.tig', '.venv', 'venv', 'env', '.env',
    '__pycache__', 'node_modules', '.idea', '.vscode',
    'build', 'dist', 'bin', 'obj', 'Debug', 'Release', 'target',
    '.gradle', '.settings', '.metadata', '.cache',
    'logs', 'tmp', 'temp', 'coverage', '.pytest_cache', '.mypy_cache', '.ruff_cache',
    'dataset', 'model', 'doc', 'Doc', 'data', 'Data', 'Dataset', 'datasets', 'Backup', 'backup'
}

EXCLUDE_FILE_PATTERNS = ['tig_snapshot_', 'project_structure_', '.tar.xz']
CLI_EXCLUDE_NAME_FRAGMENTS = ('tig_snapshot', 'tig_delta', '.bench.md')
TIG_CLI_VERSION = "1.5"
DEFAULT_DIFF_MAX_FILES = 30
DEFAULT_DIFF_MAX_LINES = 2500
DEFAULT_INDEX_MAX_ENTRIES = 50
DEFAULT_TREE_MAX_DEPTH = 2


def truncate_lines(text: str, max_lines: int, label: str = "output") -> str:
    if not text:
        return text
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    omitted = len(lines) - max_lines
    return "\n".join(lines[:max_lines]) + f"\n... [{label}: truncated, {omitted} lines omitted]"


def resolve_base_ref(git: "GitAnalyzer", preferred: str) -> Tuple[str, str]:
    candidates: List[str] = []
    for ref in (preferred, "origin/main", "main", "HEAD~1"):
        if ref and ref not in candidates:
            candidates.append(ref)
    for ref in candidates:
        if git.run_cmd(["rev-parse", "--verify", ref]):
            note = ref if ref == preferred else f"fallback:{ref} (preferred {preferred!r} missing)"
            return ref, note
    head = git.head_ref()
    if head != "no-git":
        return "HEAD", "fallback:HEAD (no merge base)"
    return "", "no-git"

# ============================================================================
# АНАЛИЗАТОР GIT
# ============================================================================
class GitAnalyzer:
    def __init__(self, repo_path):
        self.repo_path = Path(repo_path).resolve()
        self.git_root = self._find_git_root(self.repo_path)
        self.has_git = self.git_root is not None

    def _find_git_root(self, path):
        current = path
        while current != current.parent:
            if (current / '.git').exists() and (current / '.git').is_dir():
                return current
            current = current.parent
        return None

    def run_cmd(self, args):
        if not self.has_git: return ""
        try:
            result = subprocess.run(
                ['git', '-C', str(self.git_root)] + args,
                capture_output=True, text=True, encoding='utf-8', errors='replace'
            )
            return result.stdout.strip() if result.returncode == 0 else ""
        except: return ""

    def get_evolution_context(self, commit_count=5):
        if not self.has_git:
            return "Git репозиторий не обнаружен."
        context = [f"Корень репозитория: {self.git_root}", ""]
        status = self.run_cmd(['status', '-s'])
        context.append("=== ТЕКУЩИЙ СТАТУС ===\n" + (status if status else "Чисто."))
        context.append(f"\n=== ИСТОРИЯ ({commit_count} коммитов) ===")
        log_stat = self.run_cmd(['log', f'-n', str(commit_count), '--stat', '--pretty=format:%h - %an, %ar : %s'])
        context.append(log_stat if log_stat else "История пуста.")
        return "\n".join(context)

    def get_evolution_context_compact(self, commit_count: int = 12) -> str:
        if not self.has_git:
            return "Git репозиторий не обнаружен."
        return "\n".join([
            f"Корень: {self.git_root}",
            "",
            "=== STATUS ===",
            self.run_cmd(["status", "-s"]) or "Чисто.",
            "",
            f"=== LOG ({commit_count} oneline) ===",
            self.run_cmd(["log", f"-n", str(commit_count), "--oneline", "--decorate"]) or "История пуста.",
        ])

    def head_ref(self) -> str:
        return self.run_cmd(['rev-parse', 'HEAD']) or "no-git"

    def status_porcelain(self) -> str:
        return self.run_cmd(['status', '--porcelain'])

    def is_dirty(self) -> bool:
        return bool(self.status_porcelain())

    def log_since(self, base_ref: str, limit: int) -> str:
        if not self.has_git:
            return ""
        effective, _ = resolve_base_ref(self, base_ref)
        if not effective:
            return ""
        if effective == "HEAD":
            return self.run_cmd(["log", f"-n", str(limit), "--oneline", "--decorate"])
        head = self.head_ref()
        if effective == head:
            return self.run_cmd(["log", f"-n", str(limit), "--oneline", "--decorate"])
        return self.run_cmd(
            ["log", f"{effective}..HEAD", f"-n", str(limit), "--oneline", "--decorate"]
        )

    def diff_name_status(self, base_ref: str) -> str:
        if not self.has_git:
            return ""
        effective, _ = resolve_base_ref(self, base_ref)
        if not effective:
            return ""
        if effective == "HEAD":
            return self.run_cmd(["show", "--name-status", "--format=", "HEAD"]) or "(root commit)"
        diff = self.run_cmd(["diff", "--name-status", f"{effective}...HEAD"])
        if diff:
            return diff
        return self.run_cmd(["diff", "--name-status", effective, "HEAD"]) or "(no diff vs base ref)"

    def unified_diff_vs_base(self, base_ref: str, max_lines: int) -> str:
        if not self.has_git:
            return "(no git)"
        effective, note = resolve_base_ref(self, base_ref)
        if not effective:
            return "(no git ref)"
        diff = ""
        if effective == "HEAD":
            diff = self.run_cmd(["show", "HEAD", "--format=", "--unified=3"]) or ""
        else:
            diff = self.run_cmd(["diff", "--unified=3", f"{effective}...HEAD"]) or ""
            if not diff:
                diff = self.run_cmd(["diff", "--unified=3", effective, "HEAD"]) or ""
            if not diff and self.head_ref() != "no-git":
                parent = self.run_cmd(["rev-parse", "--verify", "HEAD^"])
                if not parent:
                    diff = self.run_cmd(["show", "HEAD", "--format=", "--unified=3"]) or ""
        header = f"# base: {effective} ({note})\n"
        body = diff or "(no committed diff vs base ref)"
        return truncate_lines(header + body, max_lines, "committed diff")

    def working_tree_diff(self, max_lines: int) -> str:
        if not self.has_git:
            return "(no git)"
        unstaged = self.run_cmd(["diff", "--unified=3"]) or ""
        staged = self.run_cmd(["diff", "--cached", "--unified=3"]) or ""
        parts: List[str] = []
        if staged:
            parts.append("## Staged\n" + staged)
        if unstaged:
            parts.append("## Unstaged\n" + unstaged)
        if not parts:
            return "(clean working tree diff)"
        return truncate_lines("\n\n".join(parts), max_lines, "working tree diff")

    def changed_files_vs_ref(self, base_ref: str) -> Set[str]:
        text = self.diff_name_status(base_ref)
        files: Set[str] = set()
        for line in text.splitlines():
            if line.startswith("("):
                continue
            parts = line.split("\t")
            if len(parts) >= 2:
                files.add(parts[-1].strip())
        wt = self.status_porcelain()
        for line in wt.splitlines():
            if len(line) >= 4:
                path = line[3:].strip()
                if " -> " in path:
                    path = path.split(" -> ", 1)[1]
                files.add(path)
        return {f for f in files if f}

# ============================================================================
# ЯДРО АРХИВАЦИИ (TIG ENGINE)
# ============================================================================
class TIGEngine:
    def __init__(self, callback=None):
        self.callback = callback
        self.is_running = False
        self.cancel_requested = False
        self.last_snapshot_path = None

    def log(self, message):
        if self.callback: self.callback(message)

    def should_ignore(self, path, is_dir=False):
        name = path.name
        if is_dir:
            if name in EXCLUDE_DIRS: return True
            lower_name = name.lower()
            for p in ['tig', 'test', 'dataset', 'data', 'doc', 'backup']:
                if p in lower_name: return True
        else:
            if path.suffix.lower() in EXCLUDE_EXTENSIONS: return True
            if name in EXCLUDE_DIRS: return True
            lower_name = name.lower()
            for pattern in EXCLUDE_FILE_PATTERNS:
                if pattern in lower_name: return True
        return False

    def generate_tree(self, target_path):
        tree = []
        def _walk(path, level=0):
            indent = "│   " * (level - 1) + "├── " if level > 0 else ""
            tree.append(f"{indent}{path.name}/" if path.is_dir() else f"{indent}{path.name}")
            if path.is_dir():
                try:
                    items = sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
                    for item in items:
                        if not self.should_ignore(item, item.is_dir()):
                            _walk(item, level + 1)
                except PermissionError: tree.append(f"{indent} [ОШИБКА ДОСТУПА]")
        _walk(target_path)
        return "\n".join(tree)

    def create_snapshot(self, target_dir, meta, include_git=True, git_commits=5):
        if self.is_running: return False
        self.is_running = True
        self.cancel_requested = False
        
        try:
            target_path = Path(target_dir).resolve()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = target_path / f"tig_snapshot_{target_path.name}_{timestamp}.txt"
            self.last_snapshot_path = output_file

            self.log(f"Начало снимка: {target_path}")
            
            git_context = ""
            if include_git:
                self.log("Анализ Git эволюции...")
                git_context = GitAnalyzer(target_path).get_evolution_context(git_commits)

            self.log("Сбор структуры и контента...")
            tree_str = self.generate_tree(target_path)

            with open(output_file, 'w', encoding='utf-8') as f:
                f.write("="*80 + "\n")
                f.write("TIG UNIFIED SNAPSHOT v1.3\n")
                f.write("="*80 + "\n\n")
                f.write(f"ПРОЕКТ: {target_path}\n")
                f.write(f"ДАТА:   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"ЦЕЛЬ (GOAL): {meta.get('goal', 'Не задана')}\n")
                f.write(f"ДЕЙСТВИЕ (DO): {meta.get('intent', 'Не задано')}\n")
                f.write(f"РЕЖИМ:  {meta.get('mode', 'REVIEW')} | ТИП: {meta.get('type', 'feature')}\n\n")

                if include_git:
                    f.write("="*80 + "\nЭВОЛЮЦИЯ ПРОЕКТА (GIT)\n" + "="*80 + "\n")
                    f.write(git_context + "\n\n")

                f.write("="*80 + "\nСТРУКТУРА ДИРЕКТОРИЙ\n" + "="*80 + "\n")
                f.write(tree_str + "\n\n")

                f.write("="*80 + "\nСОДЕРЖИМОЕ ФАЙЛОВ\n" + "="*80 + "\n")
                
                count = 0
                for root, dirs, files in os.walk(target_path):
                    dirs[:] = [d for d in dirs if not self.should_ignore(Path(root)/d, True)]
                    for name in files:
                        p = Path(root) / name
                        if self.should_ignore(p, False) or p == output_file: continue
                        
                        try:
                            if p.stat().st_size > MAX_FILE_SIZE: continue
                            try: content = p.read_text(encoding='utf-8', errors='replace')
                            except: content = p.read_text(encoding='latin-1', errors='replace')
                            
                            if '\x00' in content[:4096]: continue
                            
                            rel = p.relative_to(target_path)
                            f.write(f"\n--- FILE: {rel} ---\n{content}\n--- EOF: {rel} ---\n")
                            count += 1
                            self.log(f"Добавлен: {rel}")
                        except: continue
                
                f.write(f"\n{'='*80}\nИТОГО ФАЙЛОВ: {count}\n{'='*80}\n")

            self.log(f"Готово! Сохранено в:\n{output_file.name}")
            return True
        except Exception as e:
            self.log(f"Ошибка: {e}")
            return False
        finally: self.is_running = False

    def cli_should_ignore(self, path: Path, is_dir: bool = False, include_env: bool = False) -> bool:
        if self.should_ignore(path, is_dir):
            return True
        name = path.name
        if not include_env and (name.startswith('.env') or name.endswith('.env')):
            return True
        if not is_dir:
            lower = name.lower()
            for frag in CLI_EXCLUDE_NAME_FRAGMENTS:
                if frag in lower:
                    return True
        return False

    def iter_project_files(self, target_path: Path, include_env: bool = False):
        for root, dirs, files in os.walk(target_path):
            dirs[:] = [
                d for d in dirs
                if not self.cli_should_ignore(Path(root) / d, True, include_env)
            ]
            for name in files:
                p = Path(root) / name
                if self.cli_should_ignore(p, False, include_env):
                    continue
                try:
                    rel = p.relative_to(target_path).as_posix()
                except ValueError:
                    continue
                yield p, rel

    def generate_tree_cli(
        self,
        target_path: Path,
        include_env: bool = False,
        max_depth: int = DEFAULT_TREE_MAX_DEPTH,
    ) -> str:
        tree: List[str] = []

        def _walk(path: Path, level: int = 0) -> None:
            if level > max_depth:
                if path.is_dir():
                    tree.append(f"{'│   ' * (level - 1)}├── {path.name}/ …")
                return
            indent = "│   " * (level - 1) + "├── " if level > 0 else ""
            tree.append(f"{indent}{path.name}/" if path.is_dir() else f"{indent}{path.name}")
            if path.is_dir():
                try:
                    items = sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
                    for item in items:
                        if not self.cli_should_ignore(item, item.is_dir(), include_env):
                            _walk(item, level + 1)
                except PermissionError:
                    tree.append(f"{indent} [ОШИБКА ДОСТУПА]")

        _walk(target_path)
        return "\n".join(tree)

    def build_module_map(self, target_path: Path, include_env: bool) -> Tuple[List[str], int]:
        stats: Dict[str, Dict[str, int]] = defaultdict(lambda: {"files": 0, "bytes": 0})
        total = 0
        for p, rel in self.iter_project_files(target_path, include_env):
            top = rel.split("/", 1)[0] if "/" in rel else rel
            try:
                size = p.stat().st_size
            except OSError:
                size = 0
            stats[top]["files"] += 1
            stats[top]["bytes"] += size
            total += 1
        lines = ["| Module | Files | Size |", "|--------|------:|-----:|"]
        for name in sorted(stats.keys(), key=str.lower):
            row = stats[name]
            lines.append(f"| `{name}` | {row['files']} | {row['bytes']} bytes |")
        lines.append(f"\n**Total:** {total} files")
        return lines, total

    def build_compressed_file_index(
        self,
        target_path: Path,
        include_env: bool,
        changed_set: Set[str],
        max_entries: int,
    ) -> Tuple[List[str], int]:
        entries: List[Tuple[str, int, bool]] = []
        for p, rel in self.iter_project_files(target_path, include_env):
            try:
                size = p.stat().st_size
            except OSError:
                size = -1
            entries.append((rel, size, rel in changed_set))
        changed = [e for e in entries if e[2]]
        unchanged = [e for e in entries if not e[2]]
        unchanged.sort(key=lambda x: x[1], reverse=True)
        selected = changed + unchanged[: max(0, max_entries - len(changed))]
        selected.sort(key=lambda x: (not x[2], -x[1], x[0]))
        lines: List[str] = []
        if changed:
            lines.append("### Changed (vs base ref)")
            for rel, size, _ in changed:
                lines.append(f"- `{rel}` ({size} bytes)")
            lines.append("")
        lines.append("### Notable files (largest / capped index)")
        for rel, size, is_changed in selected:
            if is_changed:
                continue
            lines.append(f"- `{rel}` ({size} bytes)")
        omitted = len(entries) - len(selected)
        if omitted > 0:
            lines.append(f"\n*+{omitted} more files — see `tig_delta.md` git diff*")
        return lines, len(entries)

    def compute_fingerprint(
        self,
        target_path: Path,
        git: GitAnalyzer,
        mode: str,
        include_env: bool,
        changed_only: bool,
        base_ref: str,
    ) -> str:
        parts = [
            TIG_CLI_VERSION,
            str(target_path.resolve()),
            mode,
            str(include_env),
            str(changed_only),
            base_ref,
            git.head_ref(),
            git.status_porcelain(),
        ]
        sig: List[str] = []
        for p, rel in sorted(self.iter_project_files(target_path, include_env), key=lambda x: x[1]):
            try:
                st = p.stat()
                sig.append(f"{rel}:{st.st_size}:{int(st.st_mtime)}")
            except OSError:
                sig.append(f"{rel}:missing")
        parts.append("\n".join(sig))
        digest = hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
        return f"sha256:{digest[:16]}"

    def build_cli_snapshot(
        self,
        target_path: Path,
        git: GitAnalyzer,
        *,
        compact: bool,
        full: bool,
        changed_only: bool,
        include_env: bool,
        git_commits: int,
        base_ref: str,
        snapshot_base_ref: str,
        index_max_entries: int = DEFAULT_INDEX_MAX_ENTRIES,
        tree_max_depth: int = DEFAULT_TREE_MAX_DEPTH,
    ) -> Tuple[str, Dict[str, Any], int]:
        mode = "compact"
        if full and changed_only:
            mode = "full-changed-only"
        elif full:
            mode = "full"
        elif compact:
            mode = "compact"

        effective_base, base_note = resolve_base_ref(git, base_ref)
        changed_set: Set[str] = set()
        if changed_only:
            ref = snapshot_base_ref or effective_base or base_ref
            changed_set = git.changed_files_vs_ref(ref)
        else:
            changed_set = git.changed_files_vs_ref(effective_base or base_ref)

        fingerprint = self.compute_fingerprint(
            target_path, git, mode, include_env, changed_only, effective_base or base_ref
        )
        meta: Dict[str, Any] = {
            "tig_cli_version": TIG_CLI_VERSION,
            "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "target": str(target_path.resolve()),
            "mode": mode,
            "fingerprint": fingerprint,
            "git_head": git.head_ref(),
            "git_dirty": git.is_dirty(),
            "base_ref": effective_base or base_ref,
            "base_ref_note": base_note,
            "file_count": 0,
        }

        git_context = git.get_evolution_context_compact(git_commits)
        tree_str = self.generate_tree_cli(target_path, include_env, max_depth=tree_max_depth)
        module_lines, total_files = self.build_module_map(target_path, include_env)

        body_lines = [
            "# TIG Snapshot",
            "",
            f"**Project:** `{target_path.name}`",
            f"**Mode:** `{mode}` | **Fingerprint:** `{fingerprint}`",
            f"**Base ref:** `{meta['base_ref']}` ({base_note})",
            "",
            "## Module map",
            "",
            "\n".join(module_lines),
            "",
            "## Directory tree",
            "",
            f"*depth ≤ {tree_max_depth}*",
            "",
            "```text",
            tree_str,
            "```",
            "",
            "## Git evolution (compact)",
            "",
            "```text",
            git_context,
            "```",
            "",
        ]

        file_count = 0
        include_bodies = full and not compact
        if include_bodies:
            body_lines.extend(["## File contents", ""])
            for p, rel in self.iter_project_files(target_path, include_env):
                if changed_only and rel not in changed_set:
                    continue
                try:
                    if p.stat().st_size > MAX_FILE_SIZE:
                        body_lines.append(f"### `{rel}` (skipped: >{MAX_FILE_SIZE_MB}MB)\n")
                        continue
                    content = p.read_text(encoding="utf-8", errors="replace")
                    if "\x00" in content[:4096]:
                        continue
                    file_count += 1
                    body_lines.extend([f"### `{rel}`", "", "```", content.rstrip(), "```", ""])
                except OSError:
                    continue
        else:
            index_lines, file_count = self.build_compressed_file_index(
                target_path, include_env, changed_set, index_max_entries
            )
            body_lines.extend(["## File index (compressed)", ""])
            body_lines.extend(index_lines)

        meta["file_count"] = file_count
        meta["total_files"] = total_files
        header = "---\n" + json.dumps(meta, ensure_ascii=False, indent=2) + "\n---\n\n"
        content = header + "\n".join(body_lines)
        return content, meta, file_count

    def parse_snapshot_fingerprint(self, snapshot_path: Path) -> Optional[str]:
        if not snapshot_path.is_file():
            return None
        text = snapshot_path.read_text(encoding="utf-8", errors="replace")
        if not text.startswith("---"):
            return None
        end = text.find("\n---", 3)
        if end == -1:
            return None
        block = text[3:end].strip()
        try:
            meta = json.loads(block)
            fp = meta.get("fingerprint")
            return str(fp) if fp else None
        except json.JSONDecodeError:
            m = re.search(r'"fingerprint"\s*:\s*"([^"]+)"', block)
            return m.group(1) if m else None

    def build_delta_report(
        self,
        git: GitAnalyzer,
        *,
        base_ref: str,
        delta_log_commits: int,
        snapshot_path: Path,
        snapshot_reused: bool,
        fingerprint: str,
        diff_max_lines: int = DEFAULT_DIFF_MAX_LINES,
    ) -> str:
        effective_base, base_note = resolve_base_ref(git, base_ref)
        status = git.status_porcelain() or "(clean)"
        log_since = git.log_since(base_ref, delta_log_commits) or "(no commits)"
        diff_ns = git.diff_name_status(base_ref) or "(no diff vs base ref)"
        committed_diff = git.unified_diff_vs_base(base_ref, max(400, diff_max_lines * 3 // 4))
        wt_diff = git.working_tree_diff(min(400, diff_max_lines // 4))
        lines = [
            "---",
            json.dumps(
                {
                    "tig_cli_version": TIG_CLI_VERSION,
                    "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "base_ref": effective_base or base_ref,
                    "base_ref_note": base_note,
                    "snapshot": str(snapshot_path),
                    "snapshot_reused": snapshot_reused,
                    "fingerprint": fingerprint,
                    "git_head": git.head_ref(),
                    "git_dirty": git.is_dirty(),
                },
                ensure_ascii=False,
                indent=2,
            ),
            "---",
            "",
            "# TIG Delta Report",
            "",
            f"- **Snapshot:** `{snapshot_path.name}` ({'reused' if snapshot_reused else 'regenerated'})",
            f"- **Fingerprint:** `{fingerprint}`",
            f"- **Base ref:** `{effective_base or base_ref}` ({base_note})",
            "",
            "## Working tree",
            "",
            "```text",
            status,
            "```",
            "",
            "## Commits since base ref",
            "",
            "```text",
            log_since,
            "```",
            "",
            "## Changed files vs base ref",
            "",
            "```text",
            diff_ns,
            "```",
            "",
            "## Unified diff vs base ref",
            "",
            "```diff",
            committed_diff,
            "```",
            "",
            "## Working tree diff",
            "",
            "```diff",
            wt_diff,
            "```",
            "",
        ]
        return truncate_lines("\n".join(lines), diff_max_lines, "delta report")


def run_cli(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="TIG CLI — snapshot without GUI")
    parser.add_argument("--cli", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--target", default=".", help="Project root")
    parser.add_argument("--out", default="tig_snapshot.md", help="Snapshot output path")
    parser.add_argument("--compact", action="store_true", help="Tree + file index only")
    parser.add_argument("--full", action="store_true", help="Include file bodies")
    parser.add_argument("--changed-only", action="store_true", help="Only changed files (with --full)")
    parser.add_argument("--git-commits", type=int, default=12, help="Git log depth in snapshot")
    parser.add_argument("--reuse-if-unchanged", action="store_true", help="Skip snapshot if fingerprint matches")
    parser.add_argument("--delta", action="store_true", help="Write delta report")
    parser.add_argument("--delta-out", default="tig_delta.md", help="Delta output path")
    parser.add_argument("--base-ref", default="origin/main", help="Git base ref for delta")
    parser.add_argument("--delta-log-commits", type=int, default=20, help="Commit log depth in delta")
    parser.add_argument("--snapshot-base-ref", default="", help="Base ref for --changed-only file filter")
    parser.add_argument("--include-env", action="store_true", help="Include .env* files")
    parser.add_argument("--delta-only", action="store_true", help="Refresh delta only; reuse snapshot if present")
    parser.add_argument("--diff-max-lines", type=int, default=DEFAULT_DIFF_MAX_LINES)
    parser.add_argument("--index-max-entries", type=int, default=DEFAULT_INDEX_MAX_ENTRIES)
    args = parser.parse_args(argv)

    target_path = Path(args.target).resolve()
    if not target_path.is_dir():
        print(f"ERROR: target not found: {target_path}", file=sys.stderr)
        return 1

    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = target_path / out_path

    delta_path = Path(args.delta_out)
    if not delta_path.is_absolute():
        delta_path = target_path / delta_path

    compact = args.compact or not args.full
    engine = TIGEngine()
    git = GitAnalyzer(target_path)
    effective_base, base_note = resolve_base_ref(git, args.base_ref)
    if effective_base != args.base_ref:
        print(f"TIG: base_ref {base_note}", file=sys.stderr)

    mode_label = (
        "compact"
        if compact and not args.full
        else ("full-changed-only" if args.full and args.changed_only else "full")
    )
    fingerprint = engine.compute_fingerprint(
        target_path,
        git,
        mode_label,
        args.include_env,
        args.changed_only,
        effective_base or args.base_ref,
    )

    snapshot_reused = False
    skip_snapshot = args.delta_only and out_path.is_file()

    if skip_snapshot:
        existing_fp = engine.parse_snapshot_fingerprint(out_path)
        fingerprint = existing_fp or fingerprint
        snapshot_reused = True
        print(f"TIG: delta-only, snapshot reused: {out_path}")
    elif args.reuse_if_unchanged and out_path.is_file():
        existing_fp = engine.parse_snapshot_fingerprint(out_path)
        if existing_fp and existing_fp == fingerprint:
            snapshot_reused = True
            print(f"TIG: snapshot reused (unchanged): {out_path}")

    if not snapshot_reused:
        content, meta, _ = engine.build_cli_snapshot(
            target_path,
            git,
            compact=compact,
            full=args.full,
            changed_only=args.changed_only,
            include_env=args.include_env,
            git_commits=args.git_commits,
            base_ref=args.base_ref,
            snapshot_base_ref=args.snapshot_base_ref or effective_base or args.base_ref,
            index_max_entries=args.index_max_entries,
        )
        fingerprint = meta["fingerprint"]
        out_path.write_text(content, encoding="utf-8")
        line_count = content.count("\n") + 1
        print(
            f"TIG: snapshot written: {out_path} "
            f"({meta.get('file_count', 0)} indexed, {line_count} lines, mode={meta.get('mode')})"
        )

    if args.delta or args.delta_only:
        delta_content = engine.build_delta_report(
            git,
            base_ref=args.base_ref,
            delta_log_commits=args.delta_log_commits,
            snapshot_path=out_path,
            snapshot_reused=snapshot_reused,
            fingerprint=fingerprint,
            diff_max_lines=args.diff_max_lines,
        )
        delta_path.write_text(delta_content, encoding="utf-8")
        delta_lines = delta_content.count("\n") + 1
        print(f"TIG: delta written: {delta_path} ({delta_lines} lines)")

    return 0

# ============================================================================
# GUI ИНТЕРФЕЙС
# ============================================================================
class TIGUnifiedGUI:
    def __init__(self):
        import customtkinter as ctk
        from tkinter import filedialog, messagebox

        self._ctk = ctk
        self._filedialog = filedialog
        self._messagebox = messagebox

        self._app = ctk.CTk()
        self._app.title("TIG Unified v1.3 - Canon & Studio")
        self._app.geometry("950x750")
        self.engine = TIGEngine(callback=self.update_log)

        self.target_dir = ctk.StringVar(value=os.getcwd())
        self.goal_var = ctk.StringVar(value="Разработка проекта")
        self.intent_var = ctk.StringVar(value="Анализ текущего состояния")

        self.setup_ui()

    def mainloop(self):
        self._app.mainloop()

    def __getattr__(self, name):
        return getattr(self._app, name)

    def setup_ui(self):
        ctk = self._ctk
        root = self._app
        root.grid_columnconfigure(0, weight=1)
        root.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(root, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 10))
        ctk.CTkLabel(header, text="TIG Unified", font=ctk.CTkFont(size=26, weight="bold")).pack(side="left")
        ctk.CTkLabel(header, text="v1.3 Canon", text_color="#007acc", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=10, pady=(5, 0))

        self.tabview = ctk.CTkTabview(root)
        self.tabview.grid(row=1, column=0, sticky="nsew", padx=20, pady=10)

        self.tab_snap = self.tabview.add("Снимок (Canon)")
        self.tab_html = self.tabview.add("Инструменты")
        self.tab_vsc = self.tabview.add("VS Code")

        self._setup_snap_tab()
        self._setup_tools_tab()
        self._setup_vsc_tab()

        self.log_frame = ctk.CTkFrame(root)
        self.log_frame.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 20))
        self.log_frame.grid_columnconfigure(0, weight=1)

        self.log_text = ctk.CTkTextbox(self.log_frame, height=120, font=ctk.CTkFont(family="Consolas", size=12))
        self.log_text.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        btn_row = ctk.CTkFrame(self.log_frame, fg_color="transparent")
        btn_row.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))

        ctk.CTkButton(
            btn_row,
            text="КОПИРОВАТЬ ДЛЯ AI (Markdown)",
            fg_color="#2d5a27",
            hover_color="#1e3d1a",
            command=self.copy_for_ai,
            width=250,
        ).pack(side="left", padx=5)
        ctk.CTkButton(btn_row, text="Очистить лог", width=120, command=lambda: self.log_text.delete("1.0", "end")).pack(side="right", padx=5)

    def _setup_snap_tab(self):
        ctk = self._ctk
        self.tab_snap.grid_columnconfigure(1, weight=1)
        
        # Path
        ctk.CTkLabel(self.tab_snap, text="Проект:", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, padx=15, pady=10, sticky="w")
        path_f = ctk.CTkFrame(self.tab_snap, fg_color="transparent")
        path_f.grid(row=0, column=1, sticky="ew", padx=15)
        path_f.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(path_f, textvariable=self.target_dir).grid(row=0, column=0, sticky="ew", padx=(0,10))
        ctk.CTkButton(path_f, text="Обзор", width=80, command=self.browse_dir).grid(row=0, column=1)

        # Goal & Intent (CANON)
        ctk.CTkLabel(self.tab_snap, text="ЦЕЛЬ (GOAL):").grid(row=1, column=0, padx=15, pady=5, sticky="w")
        ctk.CTkEntry(self.tab_snap, textvariable=self.goal_var, placeholder_text="Глобальная цель проекта").grid(row=1, column=1, sticky="ew", padx=15)
        
        ctk.CTkLabel(self.tab_snap, text="ДЕЙСТВИЕ (DO):").grid(row=2, column=0, padx=15, pady=5, sticky="w")
        ctk.CTkEntry(self.tab_snap, textvariable=self.intent_var, placeholder_text="Что делаем сейчас?").grid(row=2, column=1, sticky="ew", padx=15)

        # Meta
        meta_f = ctk.CTkFrame(self.tab_snap, fg_color="transparent")
        meta_f.grid(row=3, column=0, columnspan=2, sticky="ew", padx=15, pady=10)
        
        ctk.CTkLabel(meta_f, text="Режим:").pack(side="left", padx=5)
        self.mode_var = ctk.StringVar(value="REVIEW")
        ctk.CTkOptionMenu(meta_f, variable=self.mode_var, values=["REVIEW", "DESIGN", "DEBUG", "PLAN"], width=100).pack(side="left", padx=5)
        
        ctk.CTkLabel(meta_f, text="Тип:").pack(side="left", padx=20)
        self.type_var = ctk.StringVar(value="feature")
        ctk.CTkOptionMenu(meta_f, variable=self.type_var, values=["feature", "bugfix", "refactor", "infra"], width=100).pack(side="left", padx=5)

        # Git
        self.git_inc = ctk.BooleanVar(value=True)
        ctk.CTkSwitch(self.tab_snap, text="Включить Git Эволюцию", variable=self.git_inc).grid(row=4, column=0, columnspan=2, padx=15, pady=10, sticky="w")

        # Action
        self.btn_run = ctk.CTkButton(self.tab_snap, text="СОЗДАТЬ СНИМОК (Ctrl+S)", height=50, font=ctk.CTkFont(size=16, weight="bold"), command=self.start_snap)
        self.btn_run.grid(row=5, column=0, columnspan=2, pady=20, padx=15, sticky="ew")

    def _setup_tools_tab(self):
        ctk = self._ctk
        ctk.CTkLabel(self.tab_html, text="Конвертер документов в Текст", font=ctk.CTkFont(weight="bold")).pack(pady=10)
        ctk.CTkButton(self.tab_html, text="Конвертировать HTML файл", command=self.tools_convert_html).pack(pady=5)

    def _setup_vsc_tab(self):
        ctk = self._ctk
        txt = "Для интеграции в VS Code / Codium:\n\n1. Создайте в проекте папку .vscode\n2. Создайте файл tasks.json\n3. Нажмите кнопку ниже, чтобы скопировать конфиг"
        ctk.CTkLabel(self.tab_vsc, text=txt, justify="left").pack(padx=20, pady=20)
        ctk.CTkButton(self.tab_vsc, text="Скопировать JSON конфиг", command=self.copy_vsc_config).pack(pady=10)

    def update_log(self, msg):
        self.log_text.insert("end", f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
        self.log_text.see("end")
        self._app.update_idletasks()

    def browse_dir(self):
        d = self._filedialog.askdirectory()
        if d:
            self.target_dir.set(d)

    def start_snap(self):
        meta = {'goal': self.goal_var.get(), 'intent': self.intent_var.get(), 'mode': self.mode_var.get(), 'type': self.type_var.get()}
        threading.Thread(target=lambda: self.engine.create_snapshot(self.target_dir.get(), meta, self.git_inc.get()), daemon=True).start()

    def copy_for_ai(self):
        if not self.engine.last_snapshot_path or not os.path.exists(self.engine.last_snapshot_path):
            self._messagebox.showwarning("Внимание", "Сначала создайте снимок!")
            return
        content = Path(self.engine.last_snapshot_path).read_text(encoding='utf-8')
        prompt = f"Ниже представлен технический контекст проекта (TIG Snapshot).\nПожалуйста, проанализируй его исходя из текущей цели: {self.goal_var.get()}\n\n```text\n{content}\n```"
        self._app.clipboard_clear()
        self._app.clipboard_append(prompt)
        self._messagebox.showinfo("Успех", "Контент обернут в Markdown и скопирован!")

    def copy_vsc_config(self):
        cli_cmd = (
            f'python3 "{os.path.abspath(__file__)}" --cli --target "${{workspaceFolder}}" '
            f'--out tig_snapshot.md --compact --git-commits 12 --reuse-if-unchanged '
            f'--delta --delta-out tig_delta.md --base-ref origin/main --delta-log-commits 20'
        )
        config = {
            "version": "2.0.0",
            "tasks": [{
                "label": "TIG: Refresh Context",
                "type": "shell",
                "command": cli_cmd,
                "problemMatcher": []
            }]
        }
        self._app.clipboard_clear()
        self._app.clipboard_append(json.dumps(config, indent=4))
        self._messagebox.showinfo("VS Code", "Конфигурация tasks.json скопирована!")

    def tools_convert_html(self):
        f = self._filedialog.askopenfilename(filetypes=[("HTML", "*.html")])
        if f:
            out = Path(f).with_suffix('.txt')
            # Базовый регекс-метод
            c = Path(f).read_text(encoding='utf-8', errors='ignore')
            t = re.sub(r'<[^>]*>', '', c)
            out.write_text(t, encoding='utf-8')
            self.update_log(f"Конвертировано: {out.name}")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        raise SystemExit(run_cli(sys.argv[2:]))
    app = TIGUnifiedGUI()
    app.mainloop()
