import json
from pathlib import Path

def build_structure(path: Path):
    """
    Рекурсивно строит структуру каталогов и файлов
    """
    structure = {}
    for item in path.iterdir():
        if item.is_dir():
            structure[item.name] = build_structure(item)
        else:
            structure[item.name] = "file"  # можно заменить на item.read_text() для содержимого
    return structure

if __name__ == "__main__":
    base_dir = Path("./app_gpa")
    if not base_dir.exists():
        print("Каталог ./app_gpa не найден!")
    else:
        structure = build_structure(base_dir)
        # Сохраняем в JSON
        with open("app_gpa_structure.json", "w", encoding="utf-8") as f:
            json.dump(structure, f, ensure_ascii=False, indent=2)
        print("✅ Структура ./app_gpa сохранена в app_gpa_structure.json")