"""支持的学校注册表（北电全站探测中 tier=full 的 55 所）。"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

_DATA_PATH = Path(__file__).resolve().parent / "data" / "supported_schools.json"


@lru_cache(maxsize=1)
def load_registry() -> dict[str, Any]:
    if not _DATA_PATH.is_file():
        return {
            "count": 0,
            "schools": [],
            "note": f"missing data file: {_DATA_PATH}",
        }
    return json.loads(_DATA_PATH.read_text(encoding="utf-8"))


def list_schools(
    *,
    query: Optional[str] = None,
    only_bill: bool = False,
    only_detail: bool = False,
) -> list[dict[str, Any]]:
    schools = list(load_registry().get("schools") or [])
    if query:
        q = query.strip().lower()
        schools = [
            s
            for s in schools
            if q in str(s.get("id", "")).lower() or q in str(s.get("name", "")).lower()
        ]
    if only_bill:
        schools = [s for s in schools if s.get("ok_bill")]
    if only_detail:
        schools = [s for s in schools if s.get("ok_detail")]
    return schools


def get_school(area_id: str | int) -> Optional[dict[str, Any]]:
    aid = str(area_id).strip()
    for s in load_registry().get("schools") or []:
        if str(s.get("id")) == aid:
            return s
    return None


def resolve_school(
    area_id: Optional[str | int] = None,
    area_name: Optional[str] = None,
    *,
    default_id: str = "83",
) -> dict[str, Any]:
    """
    解析学校。优先 id；其次按名称模糊匹配；最后默认江师大。
    返回至少含 id / name / campus_root 的 dict。
    """
    if area_id is not None and str(area_id).strip():
        found = get_school(area_id)
        if found:
            return dict(found)
        # 允许未收录 id（用户自测）
        return {
            "id": str(area_id).strip(),
            "name": (area_name or "").strip() or f"学校{area_id}",
            "tier": "unknown",
            "campus_root": "001001",
            "ok_balance": None,
            "ok_bill": None,
            "ok_detail": None,
        }

    if area_name:
        name = area_name.strip()
        exact = [s for s in list_schools() if s.get("name") == name]
        if exact:
            return dict(exact[0])
        fuzzy = [s for s in list_schools() if name in str(s.get("name", ""))]
        if len(fuzzy) == 1:
            return dict(fuzzy[0])
        if len(fuzzy) > 1:
            raise ValueError(
                "学校名不唯一，请用 --school-id 指定。候选: "
                + ", ".join(f"{s['id']}={s['name']}" for s in fuzzy[:8])
            )
        if name:
            return {
                "id": default_id,
                "name": name,
                "tier": "unknown",
                "campus_root": "001001",
            }

    found = get_school(default_id)
    if found:
        return dict(found)
    return {
        "id": default_id,
        "name": "江西师范大学",
        "tier": "full",
        "campus_root": "001001",
    }


def school_table_rows(
    schools: Optional[list[dict[str, Any]]] = None,
) -> list[dict[str, str]]:
    rows = []
    for s in schools if schools is not None else list_schools():
        rows.append(
            {
                "id": str(s.get("id", "")),
                "name": str(s.get("name", "")),
                "balance": "Y" if s.get("ok_balance") else "N",
                "bill": "Y" if s.get("ok_bill") else "N",
                "detail": "Y" if s.get("ok_detail") else "N",
                "campus_root": str(s.get("campus_root") or ""),
                "sample_meter": str(s.get("sample_meter") or ""),
            }
        )
    return rows
