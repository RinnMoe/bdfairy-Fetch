"""小工具：落盘 JSON、读 .env。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def save_result(result: dict[str, Any] | Any, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return path


def load_env_file(path: str | Path) -> dict[str, str]:
    """极简 .env 读取（无需 python-dotenv）。"""
    path = Path(path)
    env: dict[str, str] = {}
    if not path.is_file():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env
