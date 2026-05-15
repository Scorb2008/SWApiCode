import json
import os

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "settings.json")


def _ensure_file():
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    if not os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "w") as f:
            json.dump({}, f)


def get_setting(key: str, default=None):
    _ensure_file()
    try:
        with open(SETTINGS_FILE) as f:
            data = json.load(f)
        return data.get(key, default)
    except (json.JSONDecodeError, OSError):
        return default


def set_setting(key: str, value):
    _ensure_file()
    try:
        with open(SETTINGS_FILE) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        data = {}
    data[key] = value
    with open(SETTINGS_FILE, "w") as f:
        json.dump(data, f)
