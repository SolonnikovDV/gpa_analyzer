#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Project Archiver GUI
Утилита для создания текстового архива структуры проекта
"""

import os
import sys
import time
import threading
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import subprocess

# ============================================================================
# КОНСТАНТЫ И НАСТРОЙКИ
# ============================================================================
MAX_FILE_SIZE_MB = 10  # Максимальный размер файла для включения (МБ)
MAX_FILE_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024  # В байтах

# Расширения файлов, которые НЕ включаем
EXCLUDE_EXTENSIONS = {
    # Бинарные и временные файлы
    '.exe', '.dll', '.so', '.dylib', '.bin',
    '.o', '.obj', '.pyc', '.pyo', '.pyd', ' .json'
    '.class', '.jar', '.war', '.ear', ' .pdb', ' .txt'

    # Медиа и архивные файлы
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg',
    '.mp3', '.mp4', '.avi', '.mov', '.wav', '.flac',
    '.zip', '.tar', '.gz', '.rar', '.7z', '.bz2', ' .xz'

    # Данные и кэш
    '.db', '.sqlite', '.sqlite3', '.cache',
    '.log', '.tmp', '.temp', '.swp', '.swo',

    # Специфичные для IDE/Сборки
    '.suo', '.user', '.csproj', '.sln',
    '.xcodeproj', '.xcworkspace', '.iml', ' .toml'
}

# Папки для полного исключения
EXCLUDE_DIRS = {
    '.git',
    '__pycache__',
    'node_modules',
    '.idea',
    '.vscode',
    'build',
    'dist',
    'bin',
    'obj',
    'Debug',
    'Release',
    'target',
    '.gradle',
    '.settings',
    '.metadata',
    'venv',
    'env',
    '.env',
    '.cache',
    'logs',
    'tmp',
    'temp',
    'coverage',
    '.pytest_cache',
    '.mypy_cache',
    '.ruff_cache',
}

# ============================================================================
# ОСНОВНАЯ ЛОГИКА АРХИВАЦИИ
# ============================================================================
class ProjectArchiver:
    def __init__(self, callback=None):
        self.callback = callback
        self.is_running = False
        self.cancel_requested = False

    def log(self, message):
        """Отправка сообщения в лог"""
        if self.callback:
            self.callback(message)

    def should_ignore_dir(self, dirname):
        """Проверка, нужно ли игнорировать директорию"""
        return dirname in EXCLUDE_DIRS

    def get_tree_structure(self, target_dir):
        """Получение структуры через команду tree"""
        try:
            # Пытаемся использовать tree с исключениями
            cmd = ['tree', '-a', '--dirsfirst', '--noreport']

            # Добавляем исключения для tree
            ignore_patterns = []
            for pattern in EXCLUDE_DIRS:
                ignore_patterns.extend(['-I', pattern])

            if ignore_patterns:
                cmd.extend(ignore_patterns)

            cmd.append(str(target_dir))

            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')

            if result.returncode == 0:
                return result.stdout
            else:
                # Если tree не поддерживает -I, используем простую версию
                result = subprocess.run(['tree', '-a', '--dirsfirst', '--noreport', str(target_dir)],
                                      capture_output=True, text=True, encoding='utf-8')
                return result.stdout
        except (subprocess.SubprocessError, FileNotFoundError):
            # Если tree не установлен, генерируем простую структуру
            return self.generate_simple_structure(target_dir)

    def generate_simple_structure(self, target_dir):
        """Генерация простой структуры если tree не установлен"""
        structure = []
        target_path = Path(target_dir)

        def add_dir(path, level=0):
            indent = "│   " * (level - 1) + "├── " if level > 0 else ""

            # Добавляем текущую директорию
            if path != target_path:
                structure.append(f"{indent}{path.name}/")
            else:
                structure.append(".")

            # Добавляем файлы
            for item in sorted(path.iterdir()):
                if item.name in EXCLUDE_DIRS:
                    continue

                if item.is_file():
                    file_ext = item.suffix.lower()
                    if file_ext in EXCLUDE_EXTENSIONS:
                        continue

                    file_indent = "│   " * level + "├── "
                    structure.append(f"{file_indent}{item.name}")
                elif item.is_dir():
                    add_dir(item, level + 1)

        try:
            add_dir(target_path)
            return "\n".join(structure)
        except Exception as e:
            return f"Ошибка генерации структуры: {e}"

    def archive_project(self, target_dir, output_file=None):
        """Основная функция архивации"""
        if self.is_running:
            self.log("⚠️  Архивация уже выполняется")
            return False

        self.is_running = True
        self.cancel_requested = False

        try:
            target_path = Path(target_dir)
            if not target_path.exists():
                self.log(f"❌ Ошибка: директория '{target_dir}' не существует")
                return False

            if not target_path.is_dir():
                self.log(f"❌ Ошибка: '{target_dir}' не является директорией")
                return False

            # Создаем имя выходного файла
            if not output_file:
                folder_name = target_path.name.replace(" ", "_")
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_file = target_path / f"project_structure_{folder_name}_{timestamp}.txt"

            output_path = Path(output_file)

            # Статистика
            total_files = 0
            total_included_files = 0
            skipped_large_files = 0
            skipped_binary_files = 0
            total_size = 0

            self.log(f"📁 Начало архивации: {target_path}")
            self.log(f"📄 Выходной файл: {output_path.name}")
            self.log("-" * 50)

            # Получаем структуру дерева
            self.log("🌳 Получение структуры проекта...")
            tree_structure = self.get_tree_structure(target_path)

            with open(output_path, 'w', encoding='utf-8') as out_f:
                # Заголовок документа
                out_f.write("=" * 80 + "\n")
                out_f.write("СТРУКТУРА ПРОЕКТА И СОДЕРЖИМОЕ ФАЙЛОВ\n")
                out_f.write("=" * 80 + "\n\n")
                out_f.write(f"Директория проекта: {target_path.absolute()}\n")
                out_f.write(f"Дата создания: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                out_f.write(f"Максимальный размер файла: {MAX_FILE_SIZE_MB} МБ\n")
                out_f.write("\n" + "=" * 80 + "\n\n")

                # Добавляем структуру дерева
                out_f.write("СТРУКТУРА ПАПОК И ФАЙЛОВ (tree):\n")
                out_f.write("-" * 60 + "\n")
                out_f.write(tree_structure)
                out_f.write("\n" + "=" * 80 + "\n\n")

                # Собираем все файлы для обработки
                out_f.write("СОДЕРЖИМОЕ ФАЙЛОВ:\n")
                out_f.write("-" * 60 + "\n\n")

                all_files = []
                for root, dirs, files in os.walk(target_path, topdown=True):
                    # Игнорируем директории
                    dirs[:] = [d for d in dirs if not self.should_ignore_dir(d)]

                    for file in files:
                        file_path = Path(root) / file
                        file_ext = file_path.suffix.lower()

                        # Пропускаем файлы с исключенными расширениями
                        if file_ext in EXCLUDE_EXTENSIONS:
                            continue

                        # Пропускаем сам выходной файл
                        if file_path.absolute() == output_path.absolute():
                            continue

                        all_files.append(file_path)

                # Сортируем файлы
                all_files.sort(key=lambda x: (str(x.parent), x.name))

                # Обрабатываем каждый файл
                for file_idx, file_path in enumerate(all_files, 1):
                    if self.cancel_requested:
                        self.log("⏹️  Архивация прервана пользователем")
                        return False

                    rel_path = file_path.relative_to(target_path)
                    file_size = file_path.stat().st_size
                    total_files += 1

                    try:
                        # Пропускаем файлы больше 10 МБ
                        if file_size > MAX_FILE_SIZE:
                            out_f.write(f"\n{'=' * 60}\n")
                            out_f.write(f"⚠️  ФАЙЛ: {rel_path}\n")
                            out_f.write(f"⚠️  ПРИЧИНА: Файл слишком большой ({file_size / (1024*1024):.1f} МБ > {MAX_FILE_SIZE_MB} МБ)\n")
                            out_f.write(f"{'=' * 60}\n\n")
                            out_f.write("[СОДЕРЖАНИЕ ПРОПУЩЕНО - ФАЙЛ СЛИШКОМ БОЛЬШОЙ]\n\n")

                            skipped_large_files += 1
                            self.log(f"  ⚠️  Пропущен (большой): {rel_path} ({file_size / (1024*1024):.1f} МБ)")
                            continue

                        # Пытаемся прочитать файл как текст
                        try:
                            content = file_path.read_text(encoding='utf-8', errors='ignore')
                        except UnicodeDecodeError:
                            # Пробуем latin-1
                            content = file_path.read_text(encoding='latin-1', errors='ignore')

                        # Проверяем, не бинарный ли файл
                        if '\x00' in content[:4096]:
                            out_f.write(f"\n{'=' * 60}\n")
                            out_f.write(f"⚠️  ФАЙЛ: {rel_path}\n")
                            out_f.write(f"⚠️  ПРИЧИНА: Бинарный файл (обнаружены нулевые байты)\n")
                            out_f.write(f"{'=' * 60}\n\n")
                            out_f.write("[СОДЕРЖАНИЕ ПРОПУЩЕНО - БИНАРНЫЙ ФАЙЛ]\n\n")

                            skipped_binary_files += 1
                            self.log(f"  ⚠️  Пропущен (бинарный): {rel_path}")
                            continue

                        # Записываем заголовок файла
                        out_f.write(f"\n{'=' * 60}\n")
                        out_f.write(f"ФАЙЛ [{file_idx}]: {rel_path}\n")
                        out_f.write(f"РАЗМЕР: {file_size} байт ({file_size/1024:.1f} КБ)\n")
                        out_f.write(f"{'=' * 60}\n\n")

                        # Записываем содержимое
                        out_f.write(content)

                        # Добавляем пустую строку если файл не заканчивается на новую строку
                        if content and not content.endswith('\n'):
                            out_f.write('\n')

                        total_included_files += 1
                        total_size += file_size

                        self.log(f"  ✅ Добавлен: {rel_path} ({file_size/1024:.1f} КБ)")

                    except Exception as e:
                        self.log(f"  ❌ Ошибка обработки {rel_path}: {e}")
                        skipped_binary_files += 1

                # Итоговая статистика
                out_f.write("\n" + "=" * 80 + "\n")
                out_f.write("СТАТИСТИКА:\n")
                out_f.write("-" * 60 + "\n")
                out_f.write(f"Всего файлов в проекте: {total_files}\n")
                out_f.write(f"Файлов включено: {total_included_files}\n")
                out_f.write(f"Пропущено (большие >{MAX_FILE_SIZE_MB}МБ): {skipped_large_files}\n")
                out_f.write(f"Пропущено (бинарные/ошибки): {skipped_binary_files}\n")
                out_f.write(f"Общий размер включенных файлов: {total_size} байт ({total_size/1024:.1f} КБ)\n")
                out_f.write(f"Директория: {target_path.absolute()}\n")
                out_f.write(f"Архив создан: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                out_f.write("=" * 80 + "\n")

            self.log("-" * 50)
            self.log(f"✅ Архивация завершена успешно!")
            self.log(f"📊 Статистика:")
            self.log(f"   • Включено файлов: {total_included_files}")
            self.log(f"   • Пропущено больших (>10МБ): {skipped_large_files}")
            self.log(f"   • Пропущено бинарных: {skipped_binary_files}")
            self.log(f"   • Общий размер: {total_size/1024:.1f} КБ")
            self.log(f"📄 Файл сохранен: {output_path}")

            return True, str(output_path), {
                'total': total_files,
                'included': total_included_files,
                'skipped_large': skipped_large_files,
                'skipped_binary': skipped_binary_files,
                'total_size': total_size
            }

        except Exception as e:
            self.log(f"❌ Критическая ошибка: {e}")
            return False, str(e), None

        finally:
            self.is_running = False

    def cancel(self):
        """Запрос отмены архивации"""
        self.cancel_requested = True

# ============================================================================
# GUI ИНТЕРФЕЙС
# ============================================================================
class ArchiverGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Project Archiver GUI")
        self.root.geometry("800x600")

        # Иконка окна
        try:
            self.root.iconbitmap(default='icon.ico')
        except:
            pass

        # Создаем архиватор
        self.archiver = ProjectArchiver(callback=self.update_log)

        # Переменные
        self.target_dir = tk.StringVar(value=os.getcwd())
        self.output_file = tk.StringVar()
        self.is_archiving = False

        self.setup_ui()

    def setup_ui(self):
        """Создание интерфейса"""
        # Создаем основной фрейм
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Настраиваем grid
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)

        # Заголовок
        title_label = ttk.Label(
            main_frame,
            text="📁 Project Archiver GUI",
            font=('Helvetica', 16, 'bold')
        )
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20))

        # Директория проекта
        ttk.Label(main_frame, text="Директория проекта:").grid(
            row=1, column=0, sticky=tk.W, pady=5
        )

        dir_frame = ttk.Frame(main_frame)
        dir_frame.grid(row=1, column=1, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        dir_frame.columnconfigure(0, weight=1)

        self.dir_entry = ttk.Entry(dir_frame, textvariable=self.target_dir)
        self.dir_entry.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=(0, 5))

        ttk.Button(
            dir_frame,
            text="Обзор...",
            command=self.browse_directory,
            width=10
        ).grid(row=0, column=1)

        # Выходной файл
        ttk.Label(main_frame, text="Выходной файл:").grid(
            row=2, column=0, sticky=tk.W, pady=5
        )

        output_frame = ttk.Frame(main_frame)
        output_frame.grid(row=2, column=1, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        output_frame.columnconfigure(0, weight=1)

        self.output_entry = ttk.Entry(output_frame, textvariable=self.output_file)
        self.output_entry.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=(0, 5))

        ttk.Button(
            output_frame,
            text="Выбрать...",
            command=self.browse_output_file,
            width=10
        ).grid(row=0, column=1)

        # Информация о настройках
        info_frame = ttk.LabelFrame(main_frame, text="Настройки архивации", padding="10")
        info_frame.grid(row=3, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        info_frame.columnconfigure(0, weight=1)

        ttk.Label(info_frame, text=f"• Максимальный размер файла: {MAX_FILE_SIZE_MB} МБ").grid(
            row=0, column=0, sticky=tk.W, pady=2
        )
        ttk.Label(info_frame, text="• Бинарные файлы исключаются автоматически").grid(
            row=1, column=0, sticky=tk.W, pady=2
        )
        ttk.Label(info_frame, text="• Папки сборки и кэша исключаются").grid(
            row=2, column=0, sticky=tk.W, pady=2
        )

        # Кнопки управления
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=4, column=0, columnspan=3, pady=10)

        self.start_button = ttk.Button(
            button_frame,
            text="Начать архивацию",
            command=self.start_archiving,
            width=20
        )
        self.start_button.grid(row=0, column=0, padx=5)

        self.cancel_button = ttk.Button(
            button_frame,
            text="Прервать",
            command=self.cancel_archiving,
            width=20,
            state=tk.DISABLED
        )
        self.cancel_button.grid(row=0, column=1, padx=5)

        self.open_button = ttk.Button(
            button_frame,
            text="Открыть результат",
            command=self.open_result,
            width=20,
            state=tk.DISABLED
        )
        self.open_button.grid(row=0, column=2, padx=5)

        # Лог действий
        ttk.Label(main_frame, text="Лог выполнения:").grid(
            row=5, column=0, sticky=tk.W, pady=(10, 0)
        )

        # Создаем ScrolledText для лога
        log_frame = ttk.Frame(main_frame)
        log_frame.grid(row=6, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(5, 0))

        # Настраиваем grid для растягивания
        main_frame.rowconfigure(6, weight=1)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        # Текстовое поле с прокруткой
        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            wrap=tk.WORD,
            width=80,
            height=20,
            font=('Consolas', 10)
        )
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Статус бар
        self.status_var = tk.StringVar(value="Готов к работе")
        status_bar = ttk.Label(
            main_frame,
            textvariable=self.status_var,
            relief=tk.SUNKEN,
            anchor=tk.W
        )
        status_bar.grid(row=7, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(10, 0))

        # Привязываем обработчик закрытия окна
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def browse_directory(self):
        """Выбор директории проекта"""
        directory = filedialog.askdirectory(
            title="Выберите директорию проекта",
            initialdir=self.target_dir.get()
        )
        if directory:
            self.target_dir.set(directory)
            self.clear_output_file()

    def browse_output_file(self):
        """Выбор выходного файла"""
        initial_dir = Path(self.target_dir.get())
        if not initial_dir.exists():
            initial_dir = Path.home()

        filename = filedialog.asksaveasfilename(
            title="Выберите файл для сохранения",
            initialdir=initial_dir,
            defaultextension=".txt",
            filetypes=[("Текстовые файлы", "*.txt"), ("Все файлы", "*.*")]
        )
        if filename:
            self.output_file.set(filename)

    def clear_output_file(self):
        """Очистка поля выходного файла"""
        self.output_file.set("")

    def update_log(self, message):
        """Обновление лога"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_message = f"[{timestamp}] {message}\n"

        # Обновляем в основном потоке
        self.root.after(0, self._update_log_text, log_message)

    def _update_log_text(self, message):
        """Внутренний метод для обновления текста лога"""
        self.log_text.insert(tk.END, message)
        self.log_text.see(tk.END)  # Прокрутка вниз
        self.log_text.update()

    def start_archiving(self):
        """Запуск архивации"""
        if self.is_archiving:
            messagebox.showwarning("Внимание", "Архивация уже выполняется")
            return

        target_dir = self.target_dir.get()
        output_file = self.output_file.get() if self.output_file.get() else None

        if not target_dir or not os.path.exists(target_dir):
            messagebox.showerror("Ошибка", "Пожалуйста, выберите существующую директорию")
            return

        # Очищаем лог
        self.log_text.delete(1.0, tk.END)

        # Меняем состояние кнопок
        self.is_archiving = True
        self.start_button.config(state=tk.DISABLED)
        self.cancel_button.config(state=tk.NORMAL)
        self.open_button.config(state=tk.DISABLED)
        self.status_var.set("Архивация выполняется...")

        # Запускаем архивацию в отдельном потоке
        thread = threading.Thread(
            target=self.run_archiving,
            args=(target_dir, output_file),
            daemon=True
        )
        thread.start()

    def run_archiving(self, target_dir, output_file):
        """Запуск архивации в отдельном потоке"""
        success, result, stats = self.archiver.archive_project(target_dir, output_file)

        # Обновляем UI в основном потоке
        self.root.after(0, self._archiving_complete, success, result, stats)

    def _archiving_complete(self, success, result, stats):
        """Завершение архивации"""
        self.is_archiving = False
        self.start_button.config(state=tk.NORMAL)
        self.cancel_button.config(state=tk.DISABLED)

        if success:
            self.status_var.set("Архивация завершена успешно")
            self.open_button.config(state=tk.NORMAL)

            # Показываем статистику
            if stats:
                stats_msg = (
                    f"📊 Статистика архивации:\n"
                    f"• Всего файлов: {stats['total']}\n"
                    f"• Включено файлов: {stats['included']}\n"
                    f"• Пропущено больших (>10МБ): {stats['skipped_large']}\n"
                    f"• Пропущено бинарных: {stats['skipped_binary']}\n"
                    f"• Общий размер: {stats['total_size']/1024:.1f} КБ\n"
                    f"• Файл сохранен: {result}"
                )

                if messagebox.askyesno(
                    "Архивация завершена",
                    f"Архивация успешно завершена!\n\n{stats_msg}\n\nОткрыть файл?"
                ):
                    self.open_file(result)
        else:
            self.status_var.set(f"Ошибка: {result}")
            messagebox.showerror("Ошибка архивации", f"Произошла ошибка:\n{result}")

    def cancel_archiving(self):
        """Прерывание архивации"""
        if self.is_archiving:
            if messagebox.askyesno("Подтверждение", "Прервать архивацию?"):
                self.archiver.cancel()
                self.status_var.set("Запрошена отмена архивации...")
                self.cancel_button.config(state=tk.DISABLED)

    def open_result(self):
        """Открытие результата"""
        if self.output_file.get() and os.path.exists(self.output_file.get()):
            self.open_file(self.output_file.get())
        else:
            messagebox.showinfo("Информация", "Сначала выполните архивацию")

    def open_file(self, filepath):
        """Открытие файла в системе"""
        try:
            if sys.platform == "win32":
                os.startfile(filepath)
            elif sys.platform == "darwin":  # macOS
                subprocess.run(["open", filepath])
            else:  # Linux
                subprocess.run(["xdg-open", filepath])
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось открыть файл:\n{e}")

    def on_closing(self):
        """Обработчик закрытия окна"""
        if self.is_archiving:
            if messagebox.askyesno("Подтверждение",
                                  "Архивация еще выполняется. Закрыть приложение?"):
                self.archiver.cancel()
                self.root.destroy()
        else:
            self.root.destroy()

# ============================================================================
# ТОЧКА ВХОДА
# ============================================================================
def main():
    """Основная функция"""
    try:
        root = tk.Tk()
        app = ArchiverGUI(root)
        root.mainloop()
    except Exception as e:
        print(f"Ошибка запуска GUI: {e}")
        print("Возможно, требуется установить tkinter:")
        print("  Ubuntu/Debian: sudo apt-get install python3-tk")
        print("  CentOS/RHEL: sudo yum install python3-tk")
        print("  macOS: brew install python-tk")
        input("Нажмите Enter для выхода...")

if __name__ == "__main__":
    main()