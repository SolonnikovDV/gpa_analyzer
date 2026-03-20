#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Упаковывает весь проект в zip, сохраняя структуру.
Создаёт мапу «путь_в_архиве → исходное_расширение»; в архиве все файлы имеют расширение .txt.
Служебные каталоги (.venv, .git, __pycache__ и др.) не включаются.
"""

import os
import sys
import json
import zipfile
from pathlib import Path

# Каталоги и файлы, которые не упаковываются
EXCLUDE_DIRS = {
    ".venv",
    ".git",
    "__pycache__",
    "node_modules",
    ".cursor",
    ".idea",
    ".vscode",
    "venv",
    "env",
    ".eggs",
    "dist",
    "build",
}

EXCLUDE_FILES = {
    "packed.zip",
    "extension_map.json",
    ".agent_cache.db",
    ".agent_cache.json",
}


def _should_skip_dir(dirname: str) -> bool:
    if dirname in EXCLUDE_DIRS:
        return True
    if dirname.endswith(".egg-info"):
        return True
    return False


def pack_directory_to_txt(source_dir: str, output_zip: str) -> None:
    """
    Упаковывает source_dir в output_zip по структуре каталогов.
    Для каждого файла запоминает исходное расширение в мапе.
    В архиве все файлы сохраняются с расширением .txt.
    Каталоги из EXCLUDE_DIRS (например .venv) пропускаются.
    """
    source_path = Path(source_dir).resolve()
    if not source_path.is_dir():
        raise FileNotFoundError(f"Директория не найдена: {source_dir}")

    extension_map = {}  # путь в архиве (с .txt) -> исходное расширение (без точки, "" если нет)

    with zipfile.ZipFile(
        output_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=9
    ) as zf:
        for root, dirs, files in os.walk(source_path):
            dirs[:] = [d for d in dirs if not _should_skip_dir(d)]

            root_path = Path(root)
            for name in files:
                if name in EXCLUDE_FILES:
                    continue
                file_path = root_path / name
                try:
                    rel = file_path.relative_to(source_path)
                except ValueError:
                    continue
                rel_str = rel.as_posix()
                _, ext = os.path.splitext(name)
                original_ext = (ext or "").lstrip(".")
                # Для файлов без расширения сохраняем пустую строку

                rel_txt = Path(rel_str).with_suffix(".txt").as_posix()
                extension_map[rel_txt] = original_ext

                zf.write(file_path, rel_txt)

        # Мапу кладём в корень архива
        map_json = json.dumps(extension_map, ensure_ascii=False, indent=2)
        zf.writestr("extension_map.json", map_json.encode("utf-8"))

    print(f"Упаковано в: {output_zip}")
    print(f"Записей в мапе расширений: {len(extension_map)}")


def main():
    if len(sys.argv) < 2:
        print("Использование: python pack_to_txt.py [исходная_директория] [выходной.zip]")
        print("  Один аргумент: упаковать текущую директорию в указанный архив.")
        print("  Два аргумента: упаковать исходную директорию в архив.")
        print("  По умолчанию: python pack_to_txt.py . packed.zip")
        sys.exit(1)

    if len(sys.argv) == 2:
        source_dir = "."
        output_zip = sys.argv[1]
    else:
        source_dir = sys.argv[1]
        output_zip = sys.argv[2]

    pack_directory_to_txt(source_dir, output_zip)


if __name__ == "__main__":
    main()
