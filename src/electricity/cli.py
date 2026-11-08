#!/usr/bin/env python3
"""
长安大学（bd.bdfairy.cn areaId=65）电表查询 CLI。

楼栋/楼层/房间来自本地静态快照（默认不访问 /getB）；
表号、余额、账单、明细为动态查询。
只有 `bdfetch buildings --refresh` 才会重新抓取静态树。

示例：
  bdfetch info
  bdfetch buildings
  bdfetch buildings --refresh
  bdfetch floors --building 1号公寓 --group 003
  bdfetch rooms --building 1号公寓 --group 003 --floor 1楼
  bdfetch room --building 1号公寓 --group 003 --floor 1楼 --room <房间> --json
  bdfetch meter --meter <表号> --detail --no-dump --json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from electricity.changan import AREA_ID, AREA_NAME, get_school, load_profile
from electricity.client import DEFAULT_BASE
from electricity.meter import pretty_print_meter, query_meter
from electricity.room import (
    load_export_state,
    query_room,
    save_export,
    scan_floor,
)
from electricity.tree import (
    list_buildings,
    list_floors,
    list_rooms,
    refresh_tree,
    tree_meta,
)
from electricity.util import save_result


def _json_out(data: Any, out: Optional[str] = None, *, indent: int = 2) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=indent, default=str)
    if out:
        path = save_result(data if isinstance(data, dict) else {"data": data}, out)
        print(text)
        print(f"\n→ {path}", file=sys.stderr)
    else:
        print(text)


def _add_group_arg(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--group",
        default=None,
        help="楼栋分组：003=北院、004=东院、005=西院、006/007=渭水校区、008=混合",
    )


def cmd_info(args: argparse.Namespace) -> int:
    profile = load_profile()
    payload = {
        "school": get_school(),
        "capabilities": profile.get("capabilities"),
        "counts": profile.get("counts"),
        "groups": profile.get("groups"),
        "id_rule": profile.get("id_rule"),
        "notes": profile.get("notes"),
        "tree": tree_meta(),
        "apis": {
            "buildings": "bdfetch buildings",
            "buildings_refresh": "bdfetch buildings --refresh",
            "floors": "bdfetch floors --building <楼栋> [--group 003]",
            "rooms": "bdfetch rooms --building <楼栋> --floor <楼层> [--group 003]",
            "room_to_meter": (
                "bdfetch room --building <楼栋> --floor <楼层> --room <房间> [--group 003]"
            ),
            "balance": "bdfetch meter --meter <表号>",
            "bill": "bdfetch meter --meter <表号>",
            "detail": "bdfetch meter --meter <表号> --detail",
            "monitor": "bdfetch monitor --meter <表号> --minutes 15 --interval 30",
        },
        "base_url": args.base,
        "oauth_required": False,
    }
    _json_out(payload, args.out)
    return 0


def cmd_buildings(args: argparse.Namespace) -> int:
    if args.refresh:
        try:
            tree = refresh_tree(
                base=args.base,
                timeout=args.timeout,
                progress=lambda msg: print(msg, file=sys.stderr, flush=True),
            )
        except Exception as exc:  # noqa: BLE001
            print(f"刷新失败: {exc}", file=sys.stderr)
            return 2
        print(
            f"静态树已更新: {tree_meta().get('path')} counts={tree.get('counts')}",
            file=sys.stderr,
        )

    try:
        rows = list_buildings()
    except FileNotFoundError as exc:
        print(f"查询失败: {exc}", file=sys.stderr)
        return 2

    payload = {
        "area_id": AREA_ID,
        "area_name": AREA_NAME,
        "tree": tree_meta(),
        "count": len(rows),
        "buildings": rows,
    }
    _json_out(payload, args.out)
    return 0


def cmd_floors(args: argparse.Namespace) -> int:
    try:
        result = list_floors(args.building, group=args.group)
    except (FileNotFoundError, ValueError) as exc:
        print(f"查询失败: {exc}", file=sys.stderr)
        return 2
    payload = {
        "area_id": AREA_ID,
        "area_name": AREA_NAME,
        "tree_updated_at": tree_meta().get("updated_at"),
        "building": result["building"],
        "count": len(result["floors"]),
        "floors": result["floors"],
    }
    _json_out(payload, args.out)
    return 0


def cmd_rooms(args: argparse.Namespace) -> int:
    try:
        result = list_rooms(args.building, args.floor, group=args.group)
    except (FileNotFoundError, ValueError) as exc:
        print(f"查询失败: {exc}", file=sys.stderr)
        return 2
    payload = {
        "area_id": AREA_ID,
        "area_name": AREA_NAME,
        "tree_updated_at": tree_meta().get("updated_at"),
        "building": result["building"],
        "floor": result["floor"],
        "count": len(result["rooms"]),
        "rooms": result["rooms"],
    }
    _json_out(payload, args.out)
    return 0


def cmd_room(args: argparse.Namespace) -> int:
    if args.scan_floor:
        if not args.building or not args.floor:
            print("--scan-floor 需要 --building 与 --floor", file=sys.stderr)
            return 1
        out_path = Path(args.out or "output/room_meters.json")
        existing, _skip = load_export_state(out_path) if args.resume else ([], set())
        by_key = {f"{r['building']}|{r['floor']}|{r['room']}": r for r in existing}

        def on_record(rec: dict[str, Any]) -> None:
            k = f"{rec['building']}|{rec['floor']}|{rec['room']}"
            by_key[k] = rec
            save_export(
                out_path,
                list(by_key.values()),
                meta={
                    "area_id": AREA_ID,
                    "area_name": AREA_NAME,
                    "group": args.group,
                    "building": args.building,
                    "floor": args.floor,
                },
            )

        try:
            part = scan_floor(
                building=args.building,
                floor=args.floor,
                group=args.group,
                campus=args.campus,
                base=args.base,
                timeout=args.timeout,
                limit=args.limit,
                skip_keys=set(by_key.keys()) if args.resume else set(),
                on_record=on_record,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"扫描失败: {exc}", file=sys.stderr)
            return 2
        for rec in part:
            by_key[f"{rec['building']}|{rec['floor']}|{rec['room']}"] = rec
        save_export(
            out_path,
            list(by_key.values()),
            meta={
                "area_id": AREA_ID,
                "area_name": AREA_NAME,
                "group": args.group,
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
            building=args.building,
            floor=args.floor,
            room=args.room,
            group=args.group,
            campus=args.campus,
            base=args.base,
            timeout=args.timeout,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"查询失败: {exc}", file=sys.stderr)
        return 2

    if args.json or not result.get("meter"):
        _json_out(result, args.out)
    else:
        rec = {
            "area_id": AREA_ID,
            "area_name": AREA_NAME,
            "group": (result.get("path") or {}).get("group"),
            "group_area": (result.get("path") or {}).get("group_area"),
            "building": (result.get("path") or {}).get("building") or args.building,
            "floor": (result.get("path") or {}).get("floor") or args.floor,
            "room": (result.get("path") or {}).get("room") or args.room,
            "meter": result["meter"],
            "meters": result.get("meters"),
            "meter_rows": result.get("meter_rows"),
        }
        print(json.dumps(rec, ensure_ascii=False, indent=2))
        if args.out:
            save_result(rec, args.out)
            print(f"\n→ {args.out}", file=sys.stderr)
        meters = [str(m) for m in (result.get("meters") or [])]
        if not meters and result.get("meter"):
            meters = [str(result["meter"])]
        if args.with_balance and meters:
            labels = {
                str(r.get("comAddress")): str(
                    r.get("PipLineName") or r.get("comAddress")
                )
                for r in (result.get("meter_rows") or [])
            }
            for m in meters:
                print(
                    f"\n-- 继续查余额：{labels.get(m, m)} ({m}) --",
                    file=sys.stderr,
                )
                bal = query_meter(
                    m,
                    base=args.base,
                    timeout=args.timeout,
                    include_bill=True,
                    include_detail=False,
                    dump_dir=None,
                )
                pretty_print_meter(bal)

    return 0 if result.get("meter") or result.get("ok") else 2


def cmd_meter(args: argparse.Namespace) -> int:
    print(
        f"== 长安大学表号直查 ==  meter={args.meter}",
        file=sys.stderr,
    )
    try:
        result = query_meter(
            args.meter,
            month=args.month,
            dump_dir=None if args.no_dump else args.dump_html,
            base=args.base,
            timeout=args.timeout,
            include_bill=not args.no_bill,
            include_detail=bool(args.detail),
        )
    except Exception as exc:  # noqa: BLE001
        print(f"查询失败: {exc}", file=sys.stderr)
        return 2

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


def cmd_monitor(args: argparse.Namespace) -> int:
    deadline = datetime.now() + timedelta(minutes=args.minutes)
    samples: list[dict[str, Any]] = []
    print(
        f"监控 长安大学 meter={args.meter} "
        f"每 {args.interval}s，共 {args.minutes} 分钟",
        file=sys.stderr,
    )
    while datetime.now() < deadline:
        try:
            r = query_meter(
                args.meter,
                base=args.base,
                timeout=args.timeout,
                include_bill=False,
                include_detail=False,
                dump_dir=None,
            )
        except Exception as exc:  # noqa: BLE001
            r = {
                "ok": False,
                "error": str(exc),
                "queried_at": datetime.now().isoformat(),
            }
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
        "area_id": AREA_ID,
        "area_name": AREA_NAME,
        "meter": args.meter,
        "interval_s": args.interval,
        "minutes": args.minutes,
        "samples": samples,
    }
    out = args.out or "output/balance_monitor.json"
    path = save_result(payload, out)
    print(f"\n→ {path}  samples={len(samples)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bdfetch",
        description="长安大学（bd.bdfairy.cn areaId=65）电表查询 CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
常用示例:
  bdfetch info
  bdfetch buildings
  bdfetch buildings --refresh          # 仅结构变更时重新抓取静态树
  bdfetch floors --building 1号公寓 --group 003
  bdfetch rooms  --building 1号公寓 --group 003 --floor 1楼
  bdfetch room   --building 1号公寓 --group 003 --floor 1楼 --room <房间> --json
  bdfetch meter  --meter <表号> --detail --no-dump --json
  bdfetch monitor --meter <表号> --minutes 15 --interval 30

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

    p = sub.add_parser("info", help="长安大学能力、分组、代号规则与静态树状态")
    p.add_argument("--out", default=None)
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("buildings", help="列出楼栋（读本地静态快照）")
    p.add_argument(
        "--refresh",
        action="store_true",
        help="显式重新抓取 /getB 全树并覆盖静态快照（耗时较长）",
    )
    p.add_argument("--out", default=None)
    p.set_defaults(func=cmd_buildings)

    p = sub.add_parser("floors", help="列出某楼栋的楼层（读静态快照）")
    p.add_argument("--building", required=True, help="楼栋名或 15 位 ID")
    _add_group_arg(p)
    p.add_argument("--out", default=None)
    p.set_defaults(func=cmd_floors)

    p = sub.add_parser("rooms", help="列出某层的房间（读静态快照）")
    p.add_argument("--building", required=True)
    p.add_argument("--floor", required=True)
    _add_group_arg(p)
    p.add_argument("--out", default=None)
    p.set_defaults(func=cmd_rooms)

    p = sub.add_parser("room", help="房间 → 表号（静态树解析 + 动态绑房）")
    p.add_argument("--building", default=None)
    p.add_argument("--floor", default=None)
    p.add_argument("--room", default=None)
    _add_group_arg(p)
    p.add_argument("--campus", default=None, help="buildingInfo 前缀（默认 长安大学）")
    p.add_argument("--scan-floor", action="store_true", help="扫整层房间→表号")
    p.add_argument("--resume", action="store_true")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--with-balance", action="store_true", help="查到表号后继续查余额（多表逐个）")
    p.add_argument("--json", action="store_true")
    p.add_argument("--out", default=None)
    p.set_defaults(func=cmd_room)

    p = sub.add_parser("meter", help="表号 → 余额/月账单/日明细（动态）")
    p.add_argument("--meter", "-m", required=True, help="电表表号 comAddress")
    p.add_argument("--month", default=None, help="账单/明细月份 YYYY-MM")
    p.add_argument("--detail", action="store_true", help="额外拉日用电明细")
    p.add_argument("--no-bill", action="store_true", help="不拉月账单")
    p.add_argument("--json", action="store_true", help="只输出 JSON")
    p.add_argument("--out", default="output/meter_query.json")
    p.add_argument("--dump-html", default="output/html")
    p.add_argument("--no-dump", action="store_true")
    p.set_defaults(func=cmd_meter)

    p = sub.add_parser("monitor", help="短时轮询余额（动态）")
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
