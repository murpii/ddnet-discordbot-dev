import json
import os


def load_map(path: str) -> dict:
    """Read a {key: value} JSON file. A missing file yields an empty dict, so a
    fresh install still starts (it just has nothing configured yet)."""
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as file:
        return json.load(file)


def save_map(path: str, data: dict) -> None:
    """Write a dict to a JSON file (pretty-printed, UTF-8, trailing newline)."""
    if directory := os.path.dirname(path):
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")
