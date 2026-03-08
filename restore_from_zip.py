import zipfile
import json
from pathlib import Path
import shutil
from typing import Dict


def restore_from_zip(
    zip_path: str = "./app_gpa_backup.zip",
    target_dir: str = "./app_gpa",
    extension_map: Dict[str, str] = None
):

    zip_file = Path(zip_path)
    if not zip_file.exists():
        raise FileNotFoundError(f"ZIP не найден: {zip_path}")

    target_path = Path(target_dir)
    target_path.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_file, "r") as zipf:

        for info in zipf.infolist():

            if info.is_dir():
                continue

            rel_path = Path(info.filename)

            # ищем расширение в карте
            orig_ext = ""
            if extension_map:
                for original_path, ext in extension_map.items():
                    if Path(original_path).stem == rel_path.name:
                        orig_ext = ext
                        break

            final_path = target_path / rel_path.parent / (rel_path.name + orig_ext)
            final_path.parent.mkdir(parents=True, exist_ok=True)

            with zipf.open(info) as src, open(final_path, "wb") as dst:
                shutil.copyfileobj(src, dst)

            print(f"✅ {rel_path} → {final_path.relative_to(target_path)}")

    print(f"\n✅ Полностью восстановлено в: {target_dir}")


if __name__ == "__main__":

    with open("extension_map.json", "r", encoding="utf-8") as f:
        extension_map = json.load(f)

    restore_from_zip(
        zip_path="./app_gpa_backup.zip",
        target_dir="./app_gpa",
        extension_map=extension_map
    )

    print("\n🎉 Готово!")