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
from datetime import datetime
from pathlib import Path
import subprocess
import customtkinter as ctk
from tkinter import filedialog, messagebox

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
        if not self.has_git: return "Git репозиторий не обнаружен."
        context = [f"Корень репозитория: {self.git_root}", ""]
        status = self.run_cmd(['status', '-s'])
        context.append("=== ТЕКУЩИЙ СТАТУС ===\n" + (status if status else "Чисто."))
        context.append(f"\n=== ИСТОРИЯ ({commit_count} коммитов) ===")
        log_stat = self.run_cmd(['log', f'-n', str(commit_count), '--stat', '--pretty=format:%h - %an, %ar : %s'])
        context.append(log_stat if log_stat else "История пуста.")
        return "\n".join(context)

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

# ============================================================================
# GUI ИНТЕРФЕЙС
# ============================================================================
class TIGUnifiedGUI(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("TIG Unified v1.3 - Canon & Studio")
        self.geometry("950x750")
        self.engine = TIGEngine(callback=self.update_log)
        
        # Данные
        self.target_dir = ctk.StringVar(value=os.getcwd())
        self.goal_var = ctk.StringVar(value="Разработка проекта")
        self.intent_var = ctk.StringVar(value="Анализ текущего состояния")
        
        self.setup_ui()

    def setup_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 10))
        ctk.CTkLabel(header, text="TIG Unified", font=ctk.CTkFont(size=26, weight="bold")).pack(side="left")
        ctk.CTkLabel(header, text="v1.3 Canon", text_color="#007acc", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=10, pady=(5,0))

        # Tabs
        self.tabview = ctk.CTkTabview(self)
        self.tabview.grid(row=1, column=0, sticky="nsew", padx=20, pady=10)
        
        self.tab_snap = self.tabview.add("Снимок (Canon)")
        self.tab_html = self.tabview.add("Инструменты")
        self.tab_vsc  = self.tabview.add("VS Code")

        self._setup_snap_tab()
        self._setup_tools_tab()
        self._setup_vsc_tab()

        # Log & Buttons
        self.log_frame = ctk.CTkFrame(self)
        self.log_frame.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 20))
        self.log_frame.grid_columnconfigure(0, weight=1)
        
        self.log_text = ctk.CTkTextbox(self.log_frame, height=120, font=ctk.CTkFont(family="Consolas", size=12))
        self.log_text.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        
        btn_row = ctk.CTkFrame(self.log_frame, fg_color="transparent")
        btn_row.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        
        ctk.CTkButton(btn_row, text="КОПИРОВАТЬ ДЛЯ AI (Markdown)", fg_color="#2d5a27", hover_color="#1e3d1a", 
                      command=self.copy_for_ai, width=250).pack(side="left", padx=5)
        ctk.CTkButton(btn_row, text="Очистить лог", width=120, command=lambda: self.log_text.delete("1.0", "end")).pack(side="right", padx=5)

    def _setup_snap_tab(self):
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
        # (Упрощенная версия v1.2 для краткости)
        ctk.CTkLabel(self.tab_html, text="Конвертер документов в Текст", font=ctk.CTkFont(weight="bold")).pack(pady=10)
        ctk.CTkButton(self.tab_html, text="Конвертировать HTML файл", command=self.tools_convert_html).pack(pady=5)

    def _setup_vsc_tab(self):
        txt = "Для интеграции в VS Code / Codium:\n\n1. Создайте в проекте папку .vscode\n2. Создайте файл tasks.json\n3. Нажмите кнопку ниже, чтобы скопировать конфиг"
        ctk.CTkLabel(self.tab_vsc, text=txt, justify="left").pack(padx=20, pady=20)
        ctk.CTkButton(self.tab_vsc, text="Скопировать JSON конфиг", command=self.copy_vsc_config).pack(pady=10)

    def update_log(self, msg):
        self.log_text.insert("end", f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
        self.log_text.see("end")
        self.update_idletasks()

    def browse_dir(self):
        d = filedialog.askdirectory()
        if d: self.target_dir.set(d)

    def start_snap(self):
        meta = {'goal': self.goal_var.get(), 'intent': self.intent_var.get(), 'mode': self.mode_var.get(), 'type': self.type_var.get()}
        threading.Thread(target=lambda: self.engine.create_snapshot(self.target_dir.get(), meta, self.git_inc.get()), daemon=True).start()

    def copy_for_ai(self):
        if not self.engine.last_snapshot_path or not os.path.exists(self.engine.last_snapshot_path):
            messagebox.showwarning("Внимание", "Сначала создайте снимок!")
            return
        content = Path(self.engine.last_snapshot_path).read_text(encoding='utf-8')
        prompt = f"Ниже представлен технический контекст проекта (TIG Snapshot).\nПожалуйста, проанализируй его исходя из текущей цели: {self.goal_var.get()}\n\n```text\n{content}\n```"
        self.clipboard_clear()
        self.clipboard_append(prompt)
        messagebox.showinfo("Успех", "Контент обернут в Markdown и скопирован!")

    def copy_vsc_config(self):
        config = {
            "version": "2.0.0",
            "tasks": [{
                "label": "TIG: Create Snapshot",
                "type": "shell",
                "command": f"python3 {os.path.abspath(__file__)}",
                "problemMatcher": []
            }]
        }
        self.clipboard_clear()
        self.clipboard_append(json.dumps(config, indent=4))
        messagebox.showinfo("VS Code", "Конфигурация tasks.json скопирована!")

    def tools_convert_html(self):
        f = filedialog.askopenfilename(filetypes=[("HTML", "*.html")])
        if f:
            out = Path(f).with_suffix('.txt')
            # Базовый регекс-метод
            c = Path(f).read_text(encoding='utf-8', errors='ignore')
            t = re.sub(r'<[^>]*>', '', c)
            out.write_text(t, encoding='utf-8')
            self.update_log(f"Конвертировано: {out.name}")

if __name__ == "__main__":
    app = TIGUnifiedGUI()
    app.mainloop()
