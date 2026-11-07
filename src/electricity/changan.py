"""长安大学（bd.bdfairy.cn areaId=65）站点常量、能力档案与代号规则。"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

AREA_ID = "65"
AREA_NAME = "长安大学"
CAMPUS_ROOT = "001000"

_DATA_PATH = Path(__file__).resolve().parent / "data" / "changan.json"

# 长安大学定长代号：root(6) + group(3) + building(6) + floor(6) + room(3)
_ID_SEGMENTS = (
    ("root", 6),
    ("group", 9),
    ("building", 15),
    ("floor", 21),
    ("room", 24),
)


@lru_cache(maxsize=1)
def load_profile() -> dict[str, Any]:
    """读取长安大学能力档案；文件缺失时返回最小可用配置。"""
    if not _DATA_PATH.is_file():
        return {
            "id": AREA_ID,
            "name": AREA_NAME,
            "campus_root": CAMPUS_ROOT,
            "tier": "full",
            "groups": [],
            "notes": [f"missing data file: {_DATA_PATH}"],
        }
    return json.loads(_DATA_PATH.read_text(encoding="utf-8"))


def get_school() -> dict[str, Any]:
    """返回长安大学的基础信息（供 info / 库调用）。"""
    p = load_profile()
    return {
        "id": str(p.get("id") or AREA_ID),
        "name": p.get("name") or AREA_NAME,
        "campus_root": str(p.get("campus_root") or CAMPUS_ROOT),
        "tier": p.get("tier") or "full",
        "verified_at": p.get("verified_at"),
        "capabilities": p.get("capabilities") or {},
        "counts": p.get("counts") or {},
    }


def group_areas() -> dict[str, str]:
    """分组代号 → 观测到的区域名，例如 003→北院、006→渭水校区。"""
    return {
        str(g.get("code")): str(g.get("area") or "")
        for g in load_profile().get("groups") or []
        if g.get("code")
    }


def split_id(value: str | int) -> dict[str, str]:
    """按长安大学定长规则拆分楼栋/楼层/房间代号。

    例：``001000003000001000001001`` →
    ``root=001000, group=003, building=000001, floor=000001, room=001``。
    """
    s = str(value).strip()
    out: dict[str, str] = {}
    start = 0
    for name, end in _ID_SEGMENTS:
        if len(s) < end:
            break
        out[name] = s[start:end]
        start = end
    return out


def describe_id(value: str | int) -> str:
    """把代号拆成可读字符串，便于日志/CLI 展示。"""
    parts = split_id(value)
    return " / ".join(f"{k}={v}" for k, v in parts.items())
