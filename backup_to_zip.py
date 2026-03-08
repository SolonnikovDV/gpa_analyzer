import os
import shutil
import zipfile
import json
from pathlib import Path
from collections import defaultdict
from typing import Dict
def process_to_zip(source_dir: str = "./app_gpa", zip_path: str = "./app_gpa_backup.zip") -> Dict[str, str]:
    """
    Исправленная версия: .txt файлы НЕ трогаем, упаковываем как есть
    """
    source_path = Path(source_dir)
    if not source_path.exists():
        raise FileNotFoundError(f"Директория {source_dir} не найдена")
    
    file_extension_map: Dict[str, str] = {}
    
    print("Сканируем структуру...")
    for file_path in source_path.rglob("*"):
        if file_path.is_file():
            rel_path = file_path.relative_to(source_path)
            file_extension_map[str(rel_path)] = file_path.suffix or ""
            print(f"Найден: {rel_path} (расширение: {file_path.suffix or 'нет'})")
    
    print("\nОбрабатываем файлы...")
    txt_files = []
    for rel_path_str, orig_ext in file_extension_map.items():
        rel_path = Path(rel_path_str)
        full_path = source_path / rel_path
        
        if orig_ext.lower() == '.txt':
            # .txt НЕ меняем - добавляем как есть
            txt_files.append(str(rel_path))
            print(f"Оставлен как есть: {rel_path}")
        else:
            # Меняет только НЕ-txt на .txt
            txt_path = full_path.with_suffix('.txt')
            shutil.copy2(full_path, txt_path)
            txt_files.append(str(txt_path.relative_to(source_path)))
            print(f"Переименован: {rel_path} -> {txt_path.name}")
    
    print("\nСоздаем ZIP...")
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for txt_rel_path_str in txt_files:
            txt_rel_path = Path(txt_rel_path_str)
            full_txt_path = source_path / txt_rel_path
            
            # В архиве сохраняем ИМЕНА БЕЗ .txt для всех
            arcname = txt_rel_path.with_suffix('')  # убираем .txt из имени в архиве
            zipf.write(full_txt_path, arcname)
            print(f"В ZIP: {arcname}")
    
    print(f"\n✅ ZIP готов: {zip_path}")
    return file_extension_map

# Готовый пример использования:
if __name__ == "__main__":
    # 1. Упаковка
    extension_map = process_to_zip()
    
    # Сохраняем карту
    with open("extension_map.json", "w", encoding='utf-8') as f:
        json.dump(extension_map, f, ensure_ascii=False, indent=2)
