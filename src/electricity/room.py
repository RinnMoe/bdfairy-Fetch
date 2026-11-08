"""长安大学房间查询：静态树解析 + 动态绑房取表号。

楼栋/楼层/房间从 :mod:`electricity.tree` 的本地快照读取；
只有 ``POST /login``、``GET /selectmeter`` 等动态步骤才访问站点。
"""

from __future__ import annotations

import json
import random
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

import requests

from .changan import AREA_ID, AREA_NAME, CAMPUS_ROOT
from .client import DEFAULT_BASE
from .session import bootstrap_area, decode_body, headers_json, jload
from .tree import resolve_room


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def extract_meter_rows(html: str) -> list[dict[str, Any]]:
    """解析 /selectmeter 页面内嵌的 ``data = ref(JSON.parse('[...]'))``。

    返回原始设备记录；长安大学同一房间可能有多个表（如空调 / 照明），
    记录里的 ``PipLineName`` 会带 ``(空调)`` / ``(照明)`` 后缀。
    """
    m = re.search(
        r"data\s*=\s*ref\(\s*JSON\.parse\(\s*'((?:\\'|[^'])*)'\s*\)\s*\)",
        html,
    )
    if not m:
        m = re.search(
            r'data\s*=\s*ref\(\s*JSON\.parse\(\s*"((?:\\"|[^"])*)"\s*\)\s*\)',
            html,
        )
    if not m:
        return []
    raw = (
        m.group(1)
        .replace("\\'", "'")
        .replace('\\"', '"')
        .replace("\\\\", "\\")
    )
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in data:
        if not isinstance(item, dict):
            continue
        meter = str(item.get("comAddress") or "").strip()
        if not meter or meter in seen:
            continue
        seen.add(meter)
        rows.append(item)
    return rows


def extract_meters(html: str) -> list[str]:
    """从 /selectmeter 页面提取全部表号（保持页面顺序）。"""
    rows = extract_meter_rows(html)
    if rows:
        return [str(r["comAddress"]) for r in rows]

    # 兜底：页面结构变化/JSON 不可解析时用正则
    found: set[str] = set()
    for m in re.findall(r"comAddress['\"\s:=\)]+['\"]?(\d{8,})", html):
        found.add(m)
    for m in re.findall(r"['\"]comAddress['\"]\s*:\s*['\"](\d+)['\"]", html):
        found.add(m)
    return sorted(found)


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
    rows = extract_meter_rows(page_html)
    meters = [str(r.get("comAddress") or "").strip() for r in rows]
    meters = [m for m in meters if m]
    if not rows:
        meters = extract_meters(page_html)
        rows = [{"comAddress": m} for m in meters]
    return {
        "ok": bool(meters),
        "building_info": building_info,
        "building_id": building_id,
        "login": login,
        "page": href,
        "meters": meters,
        "meter_rows": rows,
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
    area_id: str = AREA_ID,
    area_name: str = AREA_NAME,
    base: str = DEFAULT_BASE,
    timeout: float = 20.0,
) -> dict[str, Any]:
    """长安大学：静态树解析房间 → 动态绑房取表号。"""
    path = resolve_room(building, floor, room, group=group)
    s = new_login_session(
        area_id=area_id, area_name=area_name, base=base, timeout=timeout
    )
    campus_label = campus or area_name
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
    result["campus_id"] = CAMPUS_ROOT
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
    meters: Optional[list[str]] = None,
) -> dict[str, Any]:
    rec: dict[str, Any] = {
        "building": building,
        "floor": floor,
        "room": room,
        "meter": meter,
    }
    if meters and len(meters) > 1:
        rec["meters"] = list(meters)
    return rec


def save_export(
    path: Path,
    records: list[dict[str, Any]],
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
        "fields": ["building", "floor", "room", "meter", "meters"],
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


def load_export_state(path: Path) -> tuple[list[dict[str, Any]], set[str]]:
    if not path.is_file():
        return [], set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return [], set()
    rows = data.get("records") or data.get("results") or []
    out: list[dict[str, Any]] = []
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
    area_id: str = AREA_ID,
    area_name: str = AREA_NAME,
    base: str = DEFAULT_BASE,
    delay: tuple[float, float] = (1.0, 2.5),
    timeout: float = 20.0,
    limit: int = 0,
    skip_keys: Optional[set[str]] = None,
    on_record: Optional[Callable[[dict[str, Any]], None]] = None,
    on_empty: Optional[Callable[[str], None]] = None,
) -> list[dict[str, Any]]:
    """扫整层房间 → 表号；房间列表来自静态快照，占位房间直接跳过。"""
    path = resolve_room(building, floor, group=group)
    floor_name = path["floor"]["name"]
    building_name = path["building"]["name"]
    rooms = path["rooms"]
    if limit and limit > 0:
        rooms = rooms[:limit]

    campus_label = campus or area_name
    skip_keys = skip_keys or set()
    records: list[dict[str, Any]] = []
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
            meters = [str(m) for m in (row.get("meters") or [])]
            if not meter and meters:
                meter = meters[0]
            if meter:
                rec = export_record(
                    building=building_name,
                    floor=floor_name,
                    room=room_name,
                    meter=str(meter),
                    meters=meters,
                )
                records.append(rec)
                skip_keys.add(key)
                if on_record:
                    on_record(rec)
                labels = [
                    str(r.get("PipLineName") or r.get("comAddress") or "")
                    for r in (row.get("meter_rows") or [])
                ]
                suffix = f" ({', '.join(labels)})" if labels else ""
                print(f"[{i}/{total}] {key} → {meter}{suffix}", flush=True)
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
