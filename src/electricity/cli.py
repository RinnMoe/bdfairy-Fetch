#!/usr/bin/env python3
"""
北电智慧水电（bd.bdfairy.cn）统一 CLI。

覆盖探测确认的 55 所 full 学校：表号直查余额/账单/日明细、房间级联查表号。
无需微信 OAuth。

示例：
  bdfetch schools
  bdfetch schools --query 师范
  bdfetch meter --school 83 --meter 190610004855
  bdfetch meter --school 80 --meter 220311002165 --detail
  bdfetch room --school 83 --building 2栋 --floor 3楼 --room S305
  bdfetch buildings --school 83
  bdfetch monitor --school 83 --meter 190610004855 --minutes 10
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from electricity.client import DEFAULT_BASE
from electricity.meter import pretty_print_meter, query_meter
from electricity.room import (
    detect_campus_root,
    list_buildings,
    list_floors,
    list_rooms,
    load_export_state,
    new_login_session,
    query_room,
    save_export,
    scan_floor,
)
from electricity.schools import get_school, list_schools, resolve_school, school_table_rows
from electricity.util import save_result


def _json_out(data: Any, out: Optional[str] = None, *, indent: int = 2) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=indent, default=str)
    if out:
        path = save_result(data if isinstance(data, dict) else {"data": data}, out)
        print(text)
        print(f"\n→ {path}", file=sys.stderr)
    else:
        print(text)


def _add_school_args(p: argparse.ArgumentParser, *, default_id: str = "83") -> None:
    p.add_argument(
        "--school",
        "--school-id",
        dest="school_id",
        default=None,
        help=f"学校 id（见 schools 子命令；默认 {default_id}）",
    )
    p.add_argument(
        "--school-name",
        default=None,
        help="学校名称（可模糊；与 --school 二选一）",
    )
    p.add_argument(
        "--area-id",
        default=None,
        help=argparse.SUPPRESS,  # 兼容旧参数
    )
    p.add_argument(
        "--area-name",
        default=None,
        help=argparse.SUPPRESS,
    )


def _resolve_from_args(args: argparse.Namespace, default_id: str = "83") -> dict[str, Any]:
    sid = args.school_id or getattr(args, "area_id", None)
    sname = args.school_name or getattr(args, "area_name", None)
    if sid is None and sname is None:
        sid = default_id
    return resolve_school(sid, sname, default_id=default_id)


def cmd_schools(args: argparse.Namespace) -> int:
    schools = list_schools(
        query=args.query,
        only_bill=args.only_bill,
        only_detail=args.only_detail,
    )
    if args.json:
        reg = {
            "count": len(schools),
            "updated_at": None,
            "schools": schools,
        }
        try:
            from electricity.schools import load_registry

            reg["updated_at"] = load_registry().get("updated_at")
        except Exception:
            pass
        _json_out(reg, args.out)
        return 0

    rows = school_table_rows(schools)
    if not rows:
        print("没有匹配的学校。", file=sys.stderr)
        return 1

    # 表格
    print(f"支持的 full 学校：{len(rows)} 所（表号+余额；部分学校账单 N）\n")
    print(f"{'ID':>5}  {'余额':^4} {'账单':^4} {'明细':^4}  名称")
    print("-" * 72)
    for r in rows:
        print(
            f"{r['id']:>5}  {r['balance']:^4} {r['bill']:^4} {r['detail']:^4}  {r['name']}"
        )
    if args.verbose:
        print("\n样例表号 / campus_root：")
        for r in rows:
            if r["sample_meter"]:
                print(
                    f"  {r['id']:>5}  root={r['campus_root']:<14} meter={r['sample_meter']}"
                )
    print(
        "\n用法: bdfetch meter --school <ID> --meter <表号>\n"
        "      bdfetch schools --query 江西"
    )
    if args.out:
        save_result({"count": len(rows), "schools": schools}, args.out)
        print(f"JSON → {args.out}", file=sys.stderr)
    return 0


def cmd_meter(args: argparse.Namespace) -> int:
    school = _resolve_from_args(args)
    if not args.meter:
        print("请指定 --meter 表号", file=sys.stderr)
        return 1

    known = get_school(school["id"])
    if known is None and not args.force:
        print(
            f"警告: 学校 id={school['id']} 不在 55 所 full 列表中，"
            f"仍将尝试查询（--force 可静默）。",
            file=sys.stderr,
        )

    print(
        f"== 表号直查 ==  {school.get('name')} (id={school['id']})  meter={args.meter}",
        file=sys.stderr,
    )
    try:
        result = query_meter(
            args.meter,
            area_id=str(school["id"]),
            area_name=str(school.get("name") or ""),
            month=args.month,
            dump_dir=None if args.no_dump else args.dump_html,
            base=args.base,
            timeout=args.timeout,
            include_bill=not args.no_bill,
            include_detail=bool(args.detail),
        )
    except Exception as exc:  # noqa: BLE001
        print(f"查询失败: {exc}", file=sys.stderr)
        return 1

    if args.json:
        _json_out(result, args.out)
    else:
        pretty_print_meter(result)
        if args.out:
            path = save_result(result, args.out)
            print(f"JSON → {path}")
        if not args.no_dump:
            print(f"HTML → {args.dump_html}")

    return 0 if result.get("ok") else 2


def cmd_buildings(args: argparse.Namespace) -> int:
    school = _resolve_from_args(args)
    s = new_login_session(
        area_id=str(school["id"]),
        area_name=str(school.get("name") or ""),
        base=args.base,
        timeout=args.timeout,
    )
    preferred = args.campus_id or school.get("campus_root")
    root, buildings = detect_campus_root(
        s, preferred=preferred, base=args.base, timeout=args.timeout
    )
    if not buildings:
        print("未获取到楼栋列表（级联失败）", file=sys.stderr)
        return 2
    payload = {
        "area_id": school["id"],
        "area_name": school.get("name"),
        "campus_root": root,
        "count": len(buildings),
        "buildings": buildings,
    }
    _json_out(payload, args.out)
    return 0


def cmd_floors(args: argparse.Namespace) -> int:
    school = _resolve_from_args(args)
    if not args.building:
        print("请指定 --building", file=sys.stderr)
        return 1
    s = new_login_session(
        area_id=str(school["id"]),
        area_name=str(school.get("name") or ""),
        base=args.base,
        timeout=args.timeout,
    )
    preferred = args.campus_id or school.get("campus_root")
    root, buildings = detect_campus_root(
        s, preferred=preferred, base=args.base, timeout=args.timeout
    )
    if not root:
        print("无法探测 campus_root", file=sys.stderr)
        return 2
    b = next(
        (x for x in buildings if x["name"] == args.building or args.building in x["name"]),
        None,
    )
    if not b:
        print(
            f"找不到楼栋 {args.building!r}，可选: {[x['name'] for x in buildings[:40]]}",
            file=sys.stderr,
        )
        return 1
    floors = list_floors(s, b["id"], base=args.base, timeout=args.timeout)
    payload = {
        "area_id": school["id"],
        "building": b,
        "campus_root": root,
        "count": len(floors),
        "floors": floors,
    }
    _json_out(payload, args.out)
    return 0


def cmd_rooms(args: argparse.Namespace) -> int:
    school = _resolve_from_args(args)
    if not args.building or not args.floor:
        print("请指定 --building 与 --floor", file=sys.stderr)
        return 1
    s = new_login_session(
        area_id=str(school["id"]),
        area_name=str(school.get("name") or ""),
        base=args.base,
        timeout=args.timeout,
    )
    preferred = args.campus_id or school.get("campus_root")
    root, buildings = detect_campus_root(
        s, preferred=preferred, base=args.base, timeout=args.timeout
    )
    if not root:
        print("无法探测 campus_root", file=sys.stderr)
        return 2
    b = next(
        (x for x in buildings if x["name"] == args.building or args.building in x["name"]),
        None,
    )
    if not b:
        print(f"找不到楼栋 {args.building!r}", file=sys.stderr)
        return 1
    floors = list_floors(s, b["id"], base=args.base, timeout=args.timeout)
    f = next(
        (x for x in floors if args.floor == x["name"] or args.floor in x["name"]),
        None,
    )
    if not f:
        print(
            f"找不到楼层 {args.floor!r}，可选: {[x['name'] for x in floors]}",
            file=sys.stderr,
        )
        return 1
    rooms = list_rooms(s, f["id"], base=args.base, timeout=args.timeout)
    payload = {
        "area_id": school["id"],
        "building": b,
        "floor": f,
        "campus_root": root,
        "count": len(rooms),
        "rooms": rooms,
    }
    _json_out(payload, args.out)
    return 0


def cmd_room(args: argparse.Namespace) -> int:
    school = _resolve_from_args(args)

    if args.scan_floor:
        if not args.building or not args.floor:
            print("--scan-floor 需要 --building 与 --floor", file=sys.stderr)
            return 1
        out_path = Path(args.out or "output/room_meters.json")
        existing, skip = load_export_state(out_path) if args.resume else ([], set())
        by_key = {
            f"{r['building']}|{r['floor']}|{r['room']}": r for r in existing
        }

        def on_record(rec: dict[str, str]) -> None:
            k = f"{rec['building']}|{rec['floor']}|{rec['room']}"
            by_key[k] = rec
            save_export(
                out_path,
                list(by_key.values()),
                meta={
                    "area_id": school["id"],
                    "area_name": school.get("name"),
                    "building": args.building,
                    "floor": args.floor,
                },
            )

        try:
            part = scan_floor(
                area_id=str(school["id"]),
                area_name=str(school.get("name") or ""),
                building=args.building,
                floor=args.floor,
                campus=args.campus,
                campus_id=args.campus_id or school.get("campus_root"),
                base=args.base,
                timeout=args.timeout,
                limit=args.limit,
                skip_keys=set(by_key.keys()) if args.resume else set(),
                on_record=on_record,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"扫描失败: {exc}", file=sys.stderr)
            return 1
        for rec in part:
            by_key[f"{rec['building']}|{rec['floor']}|{rec['room']}"] = rec
        save_export(
            out_path,
            list(by_key.values()),
            meta={
                "area_id": school["id"],
                "area_name": school.get("name"),
                "building": args.building,
                "floor": args.floor,
            },
        )
        print(f"\nexported {len(by_key)} records → {out_path}")
        return 0 if by_key else 2

    if not args.building or not args.floor or not args.room:
        print(
            "请指定 --building --floor --room，或使用 --scan-floor",
            file=sys.stderr,
        )
        return 1

    try:
        result = query_room(
            area_id=str(school["id"]),
            area_name=str(school.get("name") or ""),
            building=args.building,
            floor=args.floor,
            room=args.room,
            campus=args.campus,
            campus_id=args.campus_id or school.get("campus_root"),
            base=args.base,
            timeout=args.timeout,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"查询失败: {exc}", file=sys.stderr)
        return 1

    if args.json or not result.get("meter"):
        _json_out(result, args.out)
    else:
        rec = {
            "area_id": school["id"],
            "area_name": school.get("name"),
            "building": (result.get("path") or {}).get("building") or args.building,
            "floor": (result.get("path") or {}).get("floor") or args.floor,
            "room": (result.get("path") or {}).get("room") or args.room,
            "meter": result["meter"],
            "meters": result.get("meters"),
        }
        print(json.dumps(rec, ensure_ascii=False, indent=2))
        if args.out:
            save_result(rec, args.out)
            print(f"\n→ {args.out}", file=sys.stderr)
        if args.with_balance and result.get("meter"):
            print("\n-- 继续查余额 --", file=sys.stderr)
            bal = query_meter(
                str(result["meter"]),
                area_id=str(school["id"]),
                area_name=str(school.get("name") or ""),
                base=args.base,
                timeout=args.timeout,
                include_bill=True,
                include_detail=False,
                dump_dir=None,
            )
            pretty_print_meter(bal)

    return 0 if result.get("meter") or result.get("ok") else 2


def cmd_monitor(args: argparse.Namespace) -> int:
    school = _resolve_from_args(args)
    if not args.meter:
        print("请指定 --meter", file=sys.stderr)
        return 1

    deadline = datetime.now() + timedelta(minutes=args.minutes)
    samples: list[dict[str, Any]] = []
    print(
        f"监控 {school.get('name')} meter={args.meter} "
        f"每 {args.interval}s，共 {args.minutes} 分钟",
        file=sys.stderr,
    )
    while datetime.now() < deadline:
        try:
            r = query_meter(
                args.meter,
                area_id=str(school["id"]),
                area_name=str(school.get("name") or ""),
                base=args.base,
                timeout=args.timeout,
                include_bill=False,
                include_detail=False,
                dump_dir=None,
            )
        except Exception as exc:  # noqa: BLE001
            r = {"ok": False, "error": str(exc), "queried_at": datetime.now().isoformat()}
        b = r.get("balance") or {}
        row = {
            "t": r.get("queried_at") or datetime.now().isoformat(timespec="seconds"),
            "ok": r.get("ok"),
            "prepaid_yuan": b.get("prepaid_yuan"),
            "total_yuan": b.get("total_yuan"),
            "total_kwh": b.get("total_kwh"),
            "reading_time": b.get("reading_time"),
            "meter_status": b.get("meter_status"),
        }
        samples.append(row)
        print(
            f"[{row['t']}] ok={row['ok']} 余额={row['total_yuan']} "
            f"kWh={row['total_kwh']} 抄表={row['reading_time']}",
            flush=True,
        )
        if datetime.now() + timedelta(seconds=args.interval) >= deadline:
            break
        time.sleep(args.interval)

    payload = {
        "area_id": school["id"],
        "area_name": school.get("name"),
        "meter": args.meter,
        "interval_s": args.interval,
        "minutes": args.minutes,
        "samples": samples,
    }
    out = args.out or "output/balance_monitor.json"
    path = save_result(payload, out)
    print(f"\n→ {path}  samples={len(samples)}")
    return 0


def cmd_info(args: argparse.Namespace) -> int:
    """单校能力摘要。"""
    school = _resolve_from_args(args)
    known = get_school(school["id"])
    payload = {
        "school": known or school,
        "in_full_list": known is not None,
        "apis": {
            "meter_balance": "bdfetch meter --school {id} --meter <表号>",
            "meter_bill": "同上（默认含月账单；部分校 bill=N）",
            "meter_detail": "bdfetch meter --school {id} --meter <表号> --detail",
            "room_to_meter": "bdfetch room --school {id} --building .. --floor .. --room ..",
            "list_buildings": "bdfetch buildings --school {id}",
        },
        "flow": [
            "GET  /?id={areaId}",
            "POST /selectarea {areaId, areaName}",
            "POST /selectmeter {comAddress, hidType:电表}",
            "GET  /meter_main          # 余额 yffye/zydl",
            "GET  /electricbill        # 月账单",
            "POST /electricdetail      # 日明细（必须 POST）",
            "POST /getB + /login       # 房间级联 → 表号",
        ],
        "base_url": args.base or DEFAULT_BASE,
        "oauth_required": False,
        "note": "表号会话即可；充值流水等仍需微信 OAuth（本 CLI 不覆盖）",
    }
    # 填 id
    for k, v in list(payload["apis"].items()):
        payload["apis"][k] = v.replace("{id}", str(school["id"]))
    _json_out(payload, args.out)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bdfetch",
        description="北电智慧水电统一查询 CLI（55 所 full 学校 · 免微信 OAuth）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
常用示例:
  bdfetch schools
  bdfetch schools --query 江西
  bdfetch info --school 83
  bdfetch meter --school 83 --meter 190610004855
  bdfetch meter --school 80 --meter 220311002165 --detail --json
  bdfetch buildings --school 83
  bdfetch room --school 83 --building 2栋 --floor 3楼 --room S305 --with-balance
  bdfetch monitor --school 83 --meter 190610004855 --minutes 5 --interval 30

等价入口: python -m electricity <子命令> ...
        """.strip(),
    )
    parser.add_argument(
        "--base",
        default=DEFAULT_BASE,
        help=f"站点根 URL（默认 {DEFAULT_BASE}）",
    )
    parser.add_argument("--timeout", type=float, default=20.0)

    sub = parser.add_subparsers(dest="command", required=True)

    # schools
    p = sub.add_parser("schools", help="列出支持的 55 所 full 学校")
    p.add_argument("--query", "-q", default=None, help="按 id 或名称过滤")
    p.add_argument("--only-bill", action="store_true", help="仅账单可用的学校")
    p.add_argument("--only-detail", action="store_true", help="仅明细可用的学校")
    p.add_argument("--json", action="store_true")
    p.add_argument("--verbose", "-v", action="store_true")
    p.add_argument("--out", default=None)
    p.set_defaults(func=cmd_schools)

    # info
    p = sub.add_parser("info", help="查看某校能力与推荐命令")
    _add_school_args(p)
    p.add_argument("--out", default=None)
    p.set_defaults(func=cmd_info)

    # meter
    p = sub.add_parser("meter", help="表号直查余额/月账单/日明细")
    _add_school_args(p)
    p.add_argument("--meter", "-m", required=True, help="电表表号 comAddress")
    p.add_argument("--month", default=None, help="账单/明细月份 YYYY-MM")
    p.add_argument("--detail", action="store_true", help="额外拉日用电明细")
    p.add_argument("--no-bill", action="store_true", help="不拉月账单")
    p.add_argument("--json", action="store_true", help="只输出 JSON")
    p.add_argument("--out", default="output/meter_query.json")
    p.add_argument("--dump-html", default="output/html")
    p.add_argument("--no-dump", action="store_true")
    p.add_argument("--force", action="store_true", help="非 full 列表学校不警告")
    p.set_defaults(func=cmd_meter)

    # buildings / floors / rooms
    p = sub.add_parser("buildings", help="列出楼栋（房间级联第一级）")
    _add_school_args(p)
    p.add_argument("--campus-id", default=None, help="覆盖 campus_root（bID）")
    p.add_argument("--out", default=None)
    p.set_defaults(func=cmd_buildings)

    p = sub.add_parser("floors", help="列出某楼栋的楼层")
    _add_school_args(p)
    p.add_argument("--building", required=True)
    p.add_argument("--campus-id", default=None)
    p.add_argument("--out", default=None)
    p.set_defaults(func=cmd_floors)

    p = sub.add_parser("rooms", help="列出某层的房间")
    _add_school_args(p)
    p.add_argument("--building", required=True)
    p.add_argument("--floor", required=True)
    p.add_argument("--campus-id", default=None)
    p.add_argument("--out", default=None)
    p.set_defaults(func=cmd_rooms)

    # room query
    p = sub.add_parser("room", help="房间 → 表号（可再查余额）")
    _add_school_args(p)
    p.add_argument("--building", default=None)
    p.add_argument("--floor", default=None)
    p.add_argument("--room", default=None)
    p.add_argument("--campus", default=None, help="buildingInfo 前缀（默认=校名）")
    p.add_argument("--campus-id", default=None, help="覆盖 campus_root")
    p.add_argument("--scan-floor", action="store_true", help="扫整层房间→表号")
    p.add_argument("--resume", action="store_true")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--with-balance", action="store_true", help="查到表号后继续查余额")
    p.add_argument("--json", action="store_true")
    p.add_argument("--out", default=None)
    p.set_defaults(func=cmd_room)

    # monitor
    p = sub.add_parser("monitor", help="短时轮询余额（推送/曲线数据源）")
    _add_school_args(p)
    p.add_argument("--meter", "-m", required=True)
    p.add_argument("--minutes", type=float, default=15)
    p.add_argument("--interval", type=float, default=30, help="秒")
    p.add_argument("--out", default="output/balance_monitor.json")
    p.set_defaults(func=cmd_monitor)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
