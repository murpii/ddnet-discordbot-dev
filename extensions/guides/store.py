import json
import os
from typing import Optional

GUIDES_PATH = "data/config/guides.json"
STYLES = ("guide", "notice", "plain")
_KEEP = object()

# languages a guide can be translated into. English is the default + fallback.
LANGUAGES = ("en", "de", "ru")
DEFAULT_LANG = "en"


def normalize_lang(value) -> str:
    """
    Map a Discord locale ("ru-RU") or raw user input ("DE") to one of
    LANGUAGES, anything unsupported falls back to English.
    """
    code = str(value or "").lower().split("-")[0]
    return code if code in LANGUAGES else DEFAULT_LANG


def localize(by_lang: dict, lang: str, fallback: bool = True) -> Optional[str]:
    if not by_lang:
        return None
    if not fallback:
        return by_lang.get(lang) or None
    return by_lang.get(lang) or by_lang.get(DEFAULT_LANG) or next(iter(by_lang.values()))


def load_guides() -> dict:
    if not os.path.exists(GUIDES_PATH):
        return {}
    with open(GUIDES_PATH, encoding="utf-8") as file:
        return json.load(file)


def save_guides(data: dict) -> None:
    os.makedirs(os.path.dirname(GUIDES_PATH), exist_ok=True)
    with open(GUIDES_PATH, "w", encoding="utf-8", newline="\n") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")


def get_guide(name: str) -> Optional[dict]:
    return load_guides().get(name)


def guide_text(name: str, lang: str) -> Optional[str]:
    guide = get_guide(name)
    return localize(guide.get("text", {}), lang) if guide else None


def upsert_guide(name: str, aliases: list, style: str, lang: str, text: str, attachment=_KEEP) -> None:
    data = load_guides()
    entry = data.setdefault(name, {"aliases": [], "style": "guide", "text": {}})
    entry["aliases"] = aliases
    entry["style"] = style if style in STYLES else "guide"
    entry.setdefault("text", {})[lang] = text
    if attachment is not _KEEP:
        if attachment:
            entry["attachment"] = attachment
        else:
            entry.pop("attachment", None)
    save_guides(data)


def delete_guide(name: str) -> bool:
    data = load_guides()
    if name not in data:
        return False
    del data[name]
    save_guides(data)
    return True
