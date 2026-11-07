"""长安大学房间级联：根 → 分组 → 楼栋 → 楼层 → 房间 → 表号（无需微信 OAuth）。"""

from __future__ import annotations

import json
import random
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

import requests

from .changan import AREA_ID, AREA_NAME, CAMPUS_ROOT, group_areas
from .client import DEFAULT_BASE
from .session import bootstrap_area, decode_body, headers_json, jload


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def getb(
    s: requests.Session,
    body: dict,
    *,
    base: str = DEFAULT_BASE,
    timeout: float = 20.0,
) -> dict:
    base = base.rstrip("/")
    r = s.post(
        f"{base}/getB",
        json=body,
        headers=headers_json(base, "/login"),
        timeout=timeout,
    )
    text = decode_body(r).strip()
    if r.status_code != 200 or not text or text[:1] not in "{[":
        raise RuntimeError(f"/getB 失败 status={r.status_code} body={text[:120]!r}")
    return json.loads(text)


def extract_meters(html: str) -> list[str]:
    """从 /selectmeter 页面提取表号。

    长安大学页面把设备列表内嵌为
    ``const data = ref(JSON.parse('[{"comAddress":"...",...}]'))``；
    这里用正则兼容该 JSON 串，无需执行 JS。
    """
    found: set[str] = set()
    for m in re.findall(r"comAddress['\"\s:=\)]+['\"]?(\d{8,})", html):
        found.add(m)
    for m in re.findall(r"['\"]comAddress['\"]\s*:\s*['\"](\d+)['\"]", html):
        found.add(m)
    return sorted(found)


def _building_rows(data: dict) -> list[dict]:
    """把 /getB 的 floor 数组规范化为楼栋列表，并按 BuildingID 去重。"""
    out: list[dict] = []
    seen: set[str] = set()
    areas = group_areas()
    for x in (data or {}).get("floor") or []:
        bid = str(x.get("BuildingID") or "").strip()
        if not bid or bid in seen:
            continue
        seen.add(bid)
        group = bid[6:9] if len(bid) >= 9 else ""
        out.append(
            {
                "name": (x.get("BuildingName") or "").strip(),
                "id": bid,
                "group": group,
                "group_area": areas.get(group, ""),
            }
        )
    return out


def detect_campus_root(
    s: requests.Session,
    *,
    preferred: Optional[str] = None,
    base: str = DEFAULT_BASE,
    timeout: float = 15.0,
) -> tuple[Optional[str], list[dict]]:
    """查询 campus_root；长安大学固定为 001000，preferred 可覆盖。"""
    roots: list[str] = []
    for root in (preferred, CAMPUS_ROOT):
        if root and root not in roots:
            roots.append(root)
    for root in roots:
        try:
            data = getb(s, {"bID": root}, base=base, timeout=min(timeout, 12.0))
        except Exception:
            continue
        buildings = _building_rows(data)
        if buildings:
            return root, buildings
    return None, []


def resolve_campus_root(
    s: requests.Session,
    *,
    preferred: Optional[str] = None,
    base: str = DEFAULT_BASE,
    timeout: float = 20.0,
) -> Optional[str]:
    """返回可用的 campus_root：优先 preferred，回退长安大学 001000。"""
    root, _ = detect_campus_root(s, preferred=preferred, base=base, timeout=timeout)
    return root or preferred or CAMPUS_ROOT


def list_buildings(
    s: requests.Session,
    campus_id: str = CAMPUS_ROOT,
    *,
    base: str = DEFAULT_BASE,
    timeout: float = 20.0,
) -> list[dict]:
    """列出楼栋；根接口有重复条目，返回前按 BuildingID 去重。"""
    data = getb(s, {"bID": campus_id}, base=base, timeout=timeout)
    return _building_rows(data)


def list_floors(
    s: requests.Session,
    building_id: str,
    *,
    base: str = DEFAULT_BASE,
    timeout: float = 20.0,
) -> list[dict]:
    data = getb(s, {"fID": building_id}, base=base, timeout=timeout)
    return [
        {"name": (x.get("BuildingName") or "").strip(), "id": x.get("BuildingID")}
        for x in (data.get("room") or [])
        if x.get("BuildingID")
    ]


def list_rooms(
    s: requests.Session,
    floor_id: str,
    *,
    base: str = DEFAULT_BASE,
    timeout: float = 20.0,
) -> list[dict]:
    data = getb(s, {"rID1": floor_id}, base=base, timeout=timeout)
    return [
        {"name": (x.get("BuildingName") or "").strip(), "id": x.get("BuildingID")}
        for x in (data.get("room1") or [])
        if x.get("BuildingID")
    ]


def new_login_session(
    *,
    area_id: str = AREA_ID,
    area_name: str = AREA_NAME,
    base: str = DEFAULT_BASE,
    timeout: float = 20.0,
) -> requests.Session:
    s, _sa = bootstrap_area(
        area_id=area_id,
        area_name=area_name,
        base=base,
        timeout=timeout,
        unbind_if_bound=True,
    )
    return s


def _format_buildings(rows: list[dict]) -> str:
    def label(b: dict) -> str:
        area = b.get("group_area") or b.get("group") or "?"
        return f"{area}/{b.get('name')}({b.get('id')})"

    return ", ".join(label(b) for b in rows)


def match_building(
    buildings: list[dict],
    key: str,
    group: Optional[str] = None,
) -> dict:
    """按楼栋 ID / 名称匹配；同名楼栋需用 group 消歧。"""
    key = str(key).strip()
    group_key = str(group).strip().zfill(3) if group else None
    rows = [
        b
        for b in buildings
        if not group_key or str(b.get("group")) == group_key
    ]
    if not rows:
        raise ValueError(f"分组 {group!r} 下没有楼栋")

    exact = [b for b in rows if str(b.get("id")) == key or b.get("name") == key]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise ValueError("楼栋不唯一，请用 --group 指定: " + _format_buildings(exact))

    fuzzy = [b for b in rows if key in str(b.get("name") or "")]
    if len(fuzzy) == 1:
        return fuzzy[0]
    if len(fuzzy) > 1:
        raise ValueError("楼栋匹配多个，请用 --group 指定: " + _format_buildings(fuzzy))

    raise ValueError(f"找不到楼栋 {key!r}，可选: " + _format_buildings(rows[:30]))


def match_floor(floors: list[dict], key: str) -> dict:
    key = str(key).strip()
    exact = [f for f in floors if str(f.get("id")) == key or f.get("name") == key]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise ValueError(f"楼层 {key!r} 不唯一: {[f['name'] for f in exact]}")

    fuzzy = [f for f in floors if key in str(f.get("name") or "")]
    if len(fuzzy) == 1:
        return fuzzy[0]
    if len(fuzzy) > 1:
        raise ValueError(f"楼层 {key!r} 匹配多个: {[f['name'] for f in fuzzy]}")

    raise ValueError(f"找不到楼层 {key!r}，可选: {[f['name'] for f in floors]}")


def resolve_path(
    s: requests.Session,
    *,
    building: str,
    floor: str,
    room: Optional[str] = None,
    group: Optional[str] = None,
    campus_id: str = CAMPUS_ROOT,
    campus: str = AREA_NAME,
    base: str = DEFAULT_BASE,
    timeout: float = 20.0,
) -> dict[str, Any]:
    buildings = list_buildings(s, campus_id, base=base, timeout=timeout)
    b = match_building(buildings, building, group)

    floors = list_floors(s, b["id"], base=base, timeout=timeout)
    f = match_floor(floors, floor)

    rooms = list_rooms(s, f["id"], base=base, timeout=timeout)
    out: dict[str, Any] = {
        "campus": campus,
        "campus_id": campus_id,
        "building": b,
        "floor": f,
        "rooms": rooms,
    }
    if room:
        rname = str(room).replace("房", "").strip()
        rm = next(
            (
                x
                for x in rooms
                if rname == str(x["name"]).replace("房", "") or rname in str(x["name"])
            ),
            None,
        )
        if not rm:
            raise ValueError(
                f"找不到房间 {room!r}，可选: {[x['name'] for x in rooms[:30]]}"
            )
        out["room"] = rm
    return out


def bind_room_get_meters(
    s: requests.Session,
    *,
    campus: str,
    building_name: str,
    floor_name: str,
    room_name: str,
    building_id: str,
    area_name: str = AREA_NAME,
    base: str = DEFAULT_BASE,
    timeout: float = 20.0,
) -> dict[str, Any]:
    """POST /login 绑房后读 /selectmeter 页面取表号。"""
    base = base.rstrip("/")
    candidates = [
        f"{campus}|{building_name}|{floor_name}|{room_name}" if campus else "",
        f"{area_name}|{building_name}|{floor_name}|{room_name}" if area_name else "",
        f"{building_name}|{floor_name}|{room_name}",
        f"校区|{building_name}|{floor_name}|{room_name}",
    ]
    # 去重保序
    seen: set[str] = set()
    infos: list[str] = []
    for bi in candidates:
        if bi and bi not in seen:
            seen.add(bi)
            infos.append(bi)

    login: dict[str, Any] = {}
    building_info = infos[0] if infos else room_name
    for bi in infos:
        r = s.post(
            f"{base}/login",
            json={"buildingInfo": bi, "buildingID": building_id},
            headers=headers_json(base, "/login"),
            timeout=timeout,
        )
        try:
            login = jload(r)
        except Exception:
            login = {"_raw": decode_body(r)[:200]}
        if isinstance(login, dict) and login.get("href"):
            building_info = bi
            break

    if not login.get("href"):
        return {
            "ok": False,
            "building_info": building_info,
            "building_id": building_id,
            "login": login,
            "meters": [],
            "error": "login 未返回 href（可能被锁房或级联路径不对）",
        }

    href = str(login["href"]).lstrip("/")
    page = s.get(
        f"{base}/{href}",
        headers={
            "Referer": f"{base}/login",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        },
        allow_redirects=False,
        timeout=timeout,
    )
    page_html = decode_body(page)
    meters = extract_meters(page_html)
    return {
        "ok": bool(meters),
        "building_info": building_info,
        "building_id": building_id,
        "login": login,
        "page": href,
        "meters": meters,
        "meter": meters[0] if meters else None,
        "queried_at": now_iso(),
    }


def query_room(
    *,
    building: str,
    floor: str,
    room: str,
    group: Optional[str] = None,
    campus: Optional[str] = None,
    campus_id: Optional[str] = None,
    area_id: str = AREA_ID,
    area_name: str = AREA_NAME,
    base: str = DEFAULT_BASE,
    timeout: float = 20.0,
) -> dict[str, Any]:
    """长安大学：房间 → 表号。"""
    s = new_login_session(
        area_id=area_id, area_name=area_name, base=base, timeout=timeout
    )
    root = resolve_campus_root(s, preferred=campus_id, base=base, timeout=timeout)
    if not root:
        return {
            "ok": False,
            "error": "无法探测 campus_root / 楼栋列表为空",
            "meters": [],
        }
    campus_label = campus or area_name
    path = resolve_path(
        s,
        building=building,
        floor=floor,
        room=room,
        group=group,
        campus_id=root,
        campus=campus_label,
        base=base,
        timeout=timeout,
    )
    rm = path["room"]
    result = bind_room_get_meters(
        s,
        campus=campus_label,
        building_name=path["building"]["name"],
        floor_name=path["floor"]["name"],
        room_name=rm["name"],
        building_id=rm["id"],
        area_name=area_name,
        base=base,
        timeout=timeout,
    )
    result["area_id"] = area_id
    result["area_name"] = area_name
    result["campus_id"] = root
    result["path"] = {
        "group": path["building"].get("group"),
        "group_area": path["building"].get("group_area"),
        "building": path["building"]["name"],
        "floor": path["floor"]["name"],
        "room": rm["name"],
    }
    return result


def export_record(
    *,
    building: str,
    floor: str,
    room: str,
    meter: str,
) -> dict[str, str]:
    return {
        "building": building,
        "floor": floor,
        "room": room,
        "meter": meter,
    }


def save_export(
    path: Path,
    records: list[dict[str, str]],
    *,
    meta: Optional[dict] = None,
    empty_keys: Optional[list[str] | set[str]] = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    records = sorted(
        records,
        key=lambda r: (
            r.get("building") or "",
            r.get("floor") or "",
            r.get("room") or "",
        ),
    )
    payload: dict[str, Any] = {
        "updated_at": now_iso(),
        "count": len(records),
        "fields": ["building", "floor", "room", "meter"],
        "records": records,
    }
    if empty_keys is not None:
        payload["empty_keys"] = sorted(set(empty_keys))
        payload["empty_count"] = len(payload["empty_keys"])
    if meta:
        payload["meta"] = meta
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def load_export_state(path: Path) -> tuple[list[dict[str, str]], set[str]]:
    if not path.is_file():
        return [], set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return [], set()
    rows = data.get("records") or data.get("results") or []
    out: list[dict[str, str]] = []
    skip: set[str] = set()
    for r in rows:
        if not isinstance(r, dict):
            continue
        b, f, room, meter = (
            r.get("building"),
            r.get("floor"),
            r.get("room"),
            r.get("meter"),
        )
        if b and f and room and meter:
            rec = export_record(
                building=str(b), floor=str(f), room=str(room), meter=str(meter)
            )
            out.append(rec)
            skip.add(f"{rec['building']}|{rec['floor']}|{rec['room']}")
    for k in data.get("empty_keys") or []:
        if isinstance(k, str) and k:
            skip.add(k)
    return out, skip


def scan_floor(
    *,
    building: str,
    floor: str,
    group: Optional[str] = None,
    campus: Optional[str] = None,
    campus_id: Optional[str] = None,
    area_id: str = AREA_ID,
    area_name: str = AREA_NAME,
    base: str = DEFAULT_BASE,
    delay: tuple[float, float] = (1.0, 2.5),
    timeout: float = 20.0,
    limit: int = 0,
    skip_keys: Optional[set[str]] = None,
    on_record: Optional[Callable[[dict[str, str]], None]] = None,
    on_empty: Optional[Callable[[str], None]] = None,
) -> list[dict[str, str]]:
    """扫整层房间 → 表号；占位房间直接跳过，避免浪费绑房次数。"""
    s0 = new_login_session(
        area_id=area_id, area_name=area_name, base=base, timeout=timeout
    )
    root = resolve_campus_root(s0, preferred=campus_id, base=base, timeout=timeout)
    if not root:
        raise RuntimeError("无法探测 campus_root")
    campus_label = campus or area_name
    path = resolve_path(
        s0,
        building=building,
        floor=floor,
        group=group,
        campus_id=root,
        campus=campus_label,
        base=base,
        timeout=timeout,
    )
    floor_name = path["floor"]["name"]
    building_name = path["building"]["name"]
    rooms = path["rooms"]
    if limit and limit > 0:
        rooms = rooms[:limit]

    skip_keys = skip_keys or set()
    records: list[dict[str, str]] = []
    total = len(rooms)
    for i, rm in enumerate(rooms, start=1):
        room_name = rm["name"]
        key = f"{building_name}|{floor_name}|{room_name}"
        if key in skip_keys:
            continue
        if "充值前请确认" in room_name:
            skip_keys.add(key)
            print(f"[{i}/{total}] {key} → 占位房间，跳过", flush=True)
            continue
        try:
            s = new_login_session(
                area_id=area_id, area_name=area_name, base=base, timeout=timeout
            )
            row = bind_room_get_meters(
                s,
                campus=campus_label,
                building_name=building_name,
                floor_name=floor_name,
                room_name=room_name,
                building_id=rm["id"],
                area_name=area_name,
                base=base,
                timeout=timeout,
            )
            meter = row.get("meter")
            if meter:
                rec = export_record(
                    building=building_name,
                    floor=floor_name,
                    room=room_name,
                    meter=str(meter),
                )
                records.append(rec)
                skip_keys.add(key)
                if on_record:
                    on_record(rec)
                print(f"[{i}/{total}] {key} → {meter}", flush=True)
            else:
                skip_keys.add(key)
                if on_empty:
                    on_empty(key)
                print(
                    f"[{i}/{total}] {key} → empty ({row.get('error') or 'no meter'})",
                    flush=True,
                )
        except Exception as exc:  # noqa: BLE001
            print(f"[{i}/{total}] {key} → ERR {exc}", flush=True)
        if i < total:
            time.sleep(random.uniform(*delay))
    return records
