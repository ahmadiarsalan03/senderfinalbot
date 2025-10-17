from __future__ import annotations

import json
import random
from pathlib import Path

DEVICE_MODELS = [
    "iPhone 13",
    "iPhone 14",
    "iPhone 15",
    "Samsung Galaxy S23",
    "Samsung Galaxy S24",
    "Google Pixel 8",
    "OnePlus 12",
    "Xiaomi 14",
    "iPad Pro",
    "Huawei P60",
]

PLATFORMS = ["iOS", "Android", "Desktop"]
APP_VERSIONS = ["9.4.2", "9.5.1", "9.6.0", "10.0.0"]
SYSTEM_VERSIONS = ["iOS 17.4", "iOS 18.0", "Android 14", "Android 15", "Windows 11"]
LANG_CODES = ["en", "es", "de", "fr", "ru"]
TIMEZONES = ["UTC", "Europe/Berlin", "America/New_York", "Asia/Dubai", "Asia/Singapore"]
CPU_ARCH = ["arm64", "x86_64"]


def random_hex(length: int) -> str:
    return "".join(random.choice("0123456789abcdef") for _ in range(length))


def generate_agent(index: int) -> dict:
    random.seed(index * 1337)
    model = random.choice(DEVICE_MODELS)
    platform = random.choice(PLATFORMS)
    app_version = random.choice(APP_VERSIONS)
    system_version = random.choice(SYSTEM_VERSIONS)
    lang_code = random.choice(LANG_CODES)
    tz = random.choice(TIMEZONES)
    cpu = random.choice(CPU_ARCH)
    user_agent = f"{platform}/{system_version} SenderBot/{app_version} ({model}; {cpu})"
    device_id = random_hex(16)
    return {
        "device_model": model,
        "platform": platform,
        "app_version": app_version,
        "system_version": system_version,
        "lang_code": lang_code,
        "tz": tz,
        "cpu_arch": cpu,
        "user_agent": user_agent,
        "device_id": device_id,
    }


def main() -> None:
    agents = [generate_agent(i) for i in range(1, 101)]
    path = Path(__file__).resolve().parents[1] / "agents" / "agents.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(agents, indent=2), encoding="utf-8")
    print(f"Generated {len(agents)} agents into {path}")


if __name__ == "__main__":
    main()
