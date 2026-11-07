"""长安大学静态楼栋树：本地快照、查询与显式刷新。

楼栋 / 楼层 / 房间结构几乎不变，因此保存在 ``data/changan_tree.json``；
默认命令只读本地快照，只有显式 ``bdfetch buildings --refresh`` 才访问 ``/getB``。
动态数据（绑房、表号、余额、账单、明细）仍由 :mod:`electricity.room` / :mod:`electricity.meter` 实时请求。
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Optional

import requests

from .changan import CAMPUS_ROOT, group_areas
from .client import DEFAULT_BASE
from .session import bootstrap_area, decode_body, headers_json

_TREE_PATH = Path(__file__).resolve().parent / "data" / "changan_tree.json"


def tree_path() -> Path:
    return _TREE_PATH


@lru_cache(maxsize=1)
def load_tree() -> dict[str, Any]:
    """读取静态树快照；缺失时提示刷新命令。"""
    if not _TREE_PATH.is_file():
        raise FileNotFoundError(
            f"缺少静态楼栋快照: {_TREE_PATH}\n"
            "先运行 `bdfetch buildings --refresh` 生成（需要访问站点 /getB）。"
        )
    return json.loads(_TREE_PATH.read_text(encoding="utf-8"))


def clear_tree_cache() -> None:
    load_tree.cache_clear()


def tree_meta() -> dict[str, Any]:
    """返回快照元信息；缺失时 available=False，不抛异常。"""
    try:
        tree = load_tree()
    except FileNotFoundError:
        return {"available": False, "path": str(_TREE_PATH)}
    return {
        "available": True,
        "path": str(_TREE_PATH),
        "updated_at": tree.get("updated_at"),
        "source": tree.get("source"),
        "counts": tree.get("counts") or {},
    }


def _dedupe_rows(data: dict, key: str) -> list[dict]:
    rows: list[dict] = []
    seen: set[str] = set()
    for x in (data or {}).get(key) or []:
        bid = str(x.get("BuildingID") or "").strip()
        if not bid or bid in seen:
            continue
        seen.add(bid)
        rows.append({"id": bid, "name": (x.get("BuildingName") or "").strip()})
    return rows


def _building_row(b: dict) -> dict:
    floors = b.get("floors") or []
    return {
        "name": b.get("name") or "",
        "id": b.get("id") or "",
        "group": b.get("group") or "",
        "group_area": b.get("group_area") or "",
        "floor_count": len(floors),
        "room_count": sum(len(f.get("rooms") or []) for f in floors),
    }


def _format_buildings(rows: list[dict]) -> str:
    def label(b: dict) -> str:
        area = b.get("group_area") or b.get("group") or "?"
        return f"{area}/{b.get('name')}({b.get('id')})"

    return ", ".join(label(b) for b in rows)


def _find_building(building: str, group: Optional[str] = None) -> dict:
    tree = load_tree()
    rows = tree.get("buildings") or []
    key = str(building).strip()
    group_key = str(group).strip().zfill(3) if group else None
    candidates = [
        b for b in rows if not group_key or str(b.get("group")) == group_key
    ]
    if not candidates:
        raise ValueError(f"分组 {group!r} 下没有楼栋")

    exact = [b for b in candidates if str(b.get("id")) == key or b.get("name") == key]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise ValueError("楼栋不唯一，请用 --group 指定: " + _format_buildings(exact))

    fuzzy = [b for b in candidates if key in str(b.get("name") or "")]
    if len(fuzzy) == 1:
        return fuzzy[0]
    if len(fuzzy) > 1:
        raise ValueError("楼栋匹配多个，请用 --group 指定: " + _format_buildings(fuzzy))

    raise ValueError(f"找不到楼栋 {key!r}，可选: " + _format_buildings(candidates[:30]))


def _find_floor(building: dict, floor: str) -> dict:
    floors = building.get("floors") or []
    key = str(floor).strip()
    exact = [f for f in floors if str(f.get("id")) == key or f.get("name") == key]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise ValueError(f"楼层 {key!r} 不唯一: {[f.get('name') for f in exact]}")

    fuzzy = [f for f in floors if key in str(f.get("name") or "")]
    if len(fuzzy) == 1:
        return fuzzy[0]
    if len(fuzzy) > 1:
        raise ValueError(f"楼层 {key!r} 匹配多个: {[f.get('name') for f in fuzzy]}")

    raise ValueError(f"找不到楼层 {key!r}，可选: {[f.get('name') for f in floors]}")


def list_buildings(*, group: Optional[str] = None) -> list[dict]:
    """从静态快照列出楼栋（不访问网络）。"""
    tree = load_tree()
    rows = [_building_row(b) for b in tree.get("buildings") or []]
    if group:
        group_key = str(group).strip().zfill(3)
        rows = [r for r in rows if r["group"] == group_key]
    return rows


def list_floors(building: str, *, group: Optional[str] = None) -> dict:
    """从静态快照列出楼层（不访问网络）。"""
    b = _find_building(building, group)
    return {
        "building": _building_row(b),
        "floors": [
            {
                "name": f.get("name") or "",
                "id": f.get("id") or "",
                "room_count": len(f.get("rooms") or []),
            }
            for f in b.get("floors") or []
        ],
    }


def list_rooms(building: str, floor: str, *, group: Optional[str] = None) -> dict:
    """从静态快照列出房间（不访问网络）。"""
    b = _find_building(building, group)
    f = _find_floor(b, floor)
    return {
        "building": _building_row(b),
        "floor": {
            "name": f.get("name") or "",
            "id": f.get("id") or "",
            "room_count": len(f.get("rooms") or []),
        },
        "rooms": f.get("rooms") or [],
    }


def resolve_room(
    building: str,
    floor: str,
    room: Optional[str] = None,
    *,
    group: Optional[str] = None,
) -> dict[str, Any]:
    """从静态快照解析 楼栋/楼层/房间（不访问网络）。"""
    b = _find_building(building, group)
    f = _find_floor(b, floor)
    out: dict[str, Any] = {
        "building": _building_row(b),
        "floor": {
            "name": f.get("name") or "",
            "id": f.get("id") or "",
            "room_count": len(f.get("rooms") or []),
        },
        "rooms": f.get("rooms") or [],
    }
    if room:
        rooms = f.get("rooms") or []
        key = str(room).replace("房", "").strip()
        rm = next(
            (
                x
                for x in rooms
                if key == str(x.get("name") or "").replace("房", "")
                or key in str(x.get("name") or "")
            ),
            None,
        )
        if not rm:
            raise ValueError(
                f"找不到房间 {room!r}，可选: {[x.get('name') for x in rooms[:30]]}"
            )
        out["room"] = rm
    return out


def _getb(
    s: requests.Session,
    body: dict,
    *,
    base: str = DEFAULT_BASE,
    timeout: float = 20.0,
    attempts: int = 3,
) -> dict:
    last: Exception | None = None
    for i in range(attempts):
        try:
            r = s.post(
                f"{base.rstrip('/')}/getB",
                json=body,
                headers=headers_json(base, "/login"),
                timeout=timeout,
            )
            text = decode_body(r).strip()
            if r.status_code != 200 or not text or text[:1] not in "{[":
                raise RuntimeError(
                    f"/getB 失败 status={r.status_code} body={text[:120]!r}"
                )
            return json.loads(text)
        except Exception as exc:  # noqa: BLE001
            last = exc
            if i < attempts - 1:
                time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"/getB 失败 {body}: {last}")


def refresh_tree(
    *,
    base: str = DEFAULT_BASE,
    timeout: float = 20.0,
    delay: float = 0.15,
    progress: Optional[Callable[[str], None]] = None,
) -> dict[str, Any]:
    """显式抓取 /getB 全树并写入静态快照（耗时较长，仅在结构变更时使用）。"""
    say = progress or (lambda _msg: None)
    s, _sa = bootstrap_area(base=base, timeout=timeout)
    root_data = _getb(s, {"bID": CAMPUS_ROOT}, base=base, timeout=timeout)
    buildings = _dedupe_rows(root_data, "floor")
    areas = group_areas()
    errors: list[str] = []
    out_buildings: list[dict] = []
    total_floors = 0
    total_rooms = 0

    for i, b in enumerate(buildings, start=1):
        group = b["id"][6:9] if len(b["id"]) >= 9 else ""
        row: dict[str, Any] = {
            "id": b["id"],
            "name": b["name"],
            "group": group,
            "group_area": areas.get(group, ""),
            "floors": [],
        }
        try:
            floor_data = _getb(s, {"fID": b["id"]}, base=base, timeout=timeout)
            floors = _dedupe_rows(floor_data, "room")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"building {b['id']} floors: {exc}")
            say(f"[{i}/{len(buildings)}] {row['group_area']}/{row['name']} 楼层失败: {exc}")
            floors = []

        for f in floors:
            try:
                room_data = _getb(s, {"rID1": f["id"]}, base=base, timeout=timeout)
                f["rooms"] = _dedupe_rows(room_data, "room1")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"floor {f['id']} rooms: {exc}")
                say(f"  {f['name']} 房间失败: {exc}")
                f["rooms"] = []
            total_rooms += len(f["rooms"])
            time.sleep(delay)

        row["floors"] = floors
        total_floors += len(floors)
        out_buildings.append(row)
        say(
            f"[{i}/{len(buildings)}] {row['group_area']}/{row['name']} "
            f"floors={len(floors)} rooms={sum(len(f['rooms']) for f in floors)}"
        )
        time.sleep(delay)

    tree: dict[str, Any] = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "source": f"{base.rstrip('/')}/getB",
        "campus_root": CAMPUS_ROOT,
        "counts": {
            "buildings": len(out_buildings),
            "floors": total_floors,
            "rooms": total_rooms,
        },
        "errors": errors,
        "buildings": out_buildings,
    }
    _TREE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _TREE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(tree, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(_TREE_PATH)
    clear_tree_cache()
    return tree
