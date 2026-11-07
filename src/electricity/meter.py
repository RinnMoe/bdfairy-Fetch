"""长安大学表号直查：余额 / 月账单 / 日用电明细（无需微信 OAuth）。"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import requests

from .changan import AREA_ID, AREA_NAME
from .client import DEFAULT_BASE
from .session import bootstrap_area, decode_body, headers_json


def extract_refs(html: str) -> dict[str, str]:
    """从 Vue ref('...') 抽取简单字符串字段。"""
    refs: dict[str, str] = {}
    for m in re.finditer(
        r"(?:const|let|var)\s+(\w+)\s*=\s*ref\(\s*['\"]([^'\"]*)['\"]\s*\)",
        html,
    ):
        refs[m.group(1)] = m.group(2)
    return refs


def extract_bill_object(html: str) -> Optional[dict[str, Any]]:
    m = re.search(r"billData\s*=\s*ref\(\s*(\{[\s\S]*?\})\s*\)", html)
    if not m:
        return None
    raw = m.group(1)
    raw_json = re.sub(r"(\w+)\s*:", r'"\1":', raw).replace("'", '"')
    try:
        return json.loads(raw_json)
    except json.JSONDecodeError:
        out: dict[str, Any] = {}
        for k, v in re.findall(r"(\w+)\s*:\s*[\"']([^\"']*)[\"']", m.group(1)):
            out[k] = v
        return out or None


def extract_detail_comments(html: str) -> Optional[list[dict[str, Any]]]:
    """从用电明细页 comments = ref(JSON.parse('...')) 解析日明细。"""
    m = re.search(
        r"comments\s*=\s*ref\(\s*JSON\.parse\(\s*'((?:\\'|[^'])*)'\s*\)\s*\)",
        html,
    )
    if not m:
        m = re.search(
            r'comments\s*=\s*ref\(\s*JSON\.parse\(\s*"((?:\\"|[^"])*)"\s*\)\s*\)',
            html,
        )
    if not m:
        return None
    raw = m.group(1).replace("\\'", "'").replace("\\n", "\n").replace("\\\\", "\\")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, list) else None


def query_meter(
    meter: str,
    *,
    area_id: str = AREA_ID,
    area_name: str = AREA_NAME,
    month: Optional[str] = None,
    dump_dir: Optional[str | Path] = None,
    base: str = DEFAULT_BASE,
    timeout: float = 20.0,
    max_attempts: int = 3,
    include_bill: bool = True,
    include_detail: bool = False,
) -> dict[str, Any]:
    """
    长安大学表号直查。

    链路：
      GET  /?id={area_id}
      POST /selectarea
      POST /selectmeter {comAddress, hidType:电表}
      GET  /meter_main
      GET  /electricbill          （可选）
      POST /electricdetail        （可选，须 POST）
    """
    base = base.rstrip("/")
    dump_path = Path(dump_dir) if dump_dir else None
    if dump_path:
        dump_path.mkdir(parents=True, exist_ok=True)

    result: dict[str, Any] = {
        "queried_at": datetime.now().isoformat(timespec="seconds"),
        "meter": str(meter),
        "area_id": str(area_id),
        "area_name": area_name,
        "ok": False,
        "status": "error",  # valid | empty | error
        "balance": {},
        "bill": None,
        "detail": None,
        "raw_refs": {},
        "errors": [],
    }

    last_error = ""
    last_status = "error"
    attempts = max(1, int(max_attempts))
    session: Optional[requests.Session] = None

    for attempt in range(1, attempts + 1):
        try:
            s, sa = bootstrap_area(
                area_id=str(area_id),
                area_name=area_name,
                base=base,
                timeout=timeout,
            )
            session = s
            result["selectarea"] = sa
            result["session_cookie"] = bool(s.cookies.get("connect.sid"))

            r = s.post(
                f"{base}/selectmeter",
                json={"comAddress": str(meter), "hidType": "电表", "room": ""},
                headers=headers_json(base, "/login"),
                timeout=timeout,
            )
            try:
                sm = r.json()
            except Exception:
                last_error = "selectmeter 非 JSON"
                last_status = "error"
                result["selectmeter"] = {"text": decode_body(r)[:200]}
                continue

            result["selectmeter"] = sm
            sm_msg = str(sm.get("msg") or sm.get("message") or sm.get("error") or "")
            if sm_msg and not sm.get("url"):
                last_error = f"selectmeter 拒绝: {sm_msg[:120]}"
                last_status = "empty"
                continue

            path = sm.get("url") or "/meter_main"
            if not str(path).startswith("/"):
                path = "/" + str(path)
            result["balance_path"] = path

            r = s.get(
                base + path,
                headers={
                    "Referer": f"{base}/selectmeter",
                    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                },
                allow_redirects=False,
                timeout=timeout,
            )
        except requests.Timeout as exc:
            last_error = f"timeout: {exc}"
            last_status = "empty" if result.get("selectmeter") else "error"
            continue
        except requests.RequestException as exc:
            last_error = f"network: {exc}"
            last_status = "error"
            continue

        html = decode_body(r)
        if dump_path:
            (dump_path / "meter_main.html").write_text(html, encoding="utf-8")

        looks_error = (
            r.status_code != 200
            or "errorApp" in html
            or ("操作失败" in html and "yffye" not in html)
        )
        refs = extract_refs(html)
        has_reading = bool(refs.get("yffye") or refs.get("zydl"))
        if looks_error or not has_reading:
            last_error = f"meter_main 无数据 attempt={attempt} status={r.status_code}"
            last_status = "empty" if (looks_error or r.status_code == 200) else "error"
            if r.status_code == 500 or "errorApp" in html:
                last_status = "error"
            continue

        result["raw_refs"] = refs

        def _clean(v: Optional[str]) -> Optional[str]:
            if v is None:
                return None
            s = str(v).strip()
            if s.lower() in ("", "undefined", "null", "none"):
                return None
            return s

        result["balance"] = {
            "prepaid_yuan": _clean(refs.get("yffye")),
            "subsidy_yuan": _clean(refs.get("bzdye")),
            "total_yuan": _clean(refs.get("zye")),
            "total_kwh": _clean(refs.get("zydl")),
            "meter_status": _clean(refs.get("dbzt")),
            "reading_time": _clean(refs.get("cbsj")),
            "room": _clean(refs.get("roomaddr")),
            "charge_type": _clean(refs.get("chargeType")),
        }
        result["ok"] = True
        result["status"] = "valid"
        break
    else:
        result["errors"].append(last_error or "meter_main 多次重试仍失败")
        result["status"] = last_status
        result["ok"] = False
        return result

    assert session is not None
    s = session

    if include_bill:
        try:
            r = s.get(
                f"{base}/electricbill",
                headers={"Referer": f"{base}/meter_main"},
                allow_redirects=False,
                timeout=timeout,
            )
            html = decode_body(r)
            if dump_path and r.status_code == 200:
                (dump_path / "electricbill.html").write_text(html, encoding="utf-8")
            if r.status_code == 200 and "errorApp" not in html and "billData" in html:
                bill = extract_bill_object(html)
                month_m = re.search(
                    r"month\s*=\s*ref\(\s*[\"']([^\"']+)[\"']\s*\)", html
                )
                default_month = month_m.group(1) if month_m else None
                result["bill"] = {
                    "month": default_month,
                    "data": bill,
                    "labels": {
                        "qcdl": "期初示数(度)",
                        "qmdl": "期末示数(度)",
                        "ydl": "用电量(度)",
                        "ydje": "用电金额(元)",
                    },
                }
                if month and month != default_month:
                    rr = s.post(
                        f"{base}/electricbill",
                        json={"month": month, "comAddress": str(meter)},
                        headers=headers_json(base, "/electricbill"),
                        timeout=timeout,
                    )
                    try:
                        result["bill"]["query_month"] = month
                        result["bill"]["query_response"] = rr.json()
                    except Exception:
                        result["bill"]["query_response_text"] = decode_body(rr)[:500]
            elif r.status_code != 200 or "errorApp" in html:
                result["errors"].append(
                    f"月账单不可用 status={r.status_code}"
                )
        except Exception as exc:  # noqa: BLE001
            result["errors"].append(f"月账单查询失败: {exc}")

    if include_detail:
        detail_month = month or datetime.now().strftime("%Y-%m")
        try:
            rd = s.post(
                f"{base}/electricdetail",
                data={"month": detail_month, "comAddress": str(meter)},
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Origin": base,
                    "Referer": f"{base}/meter_main",
                    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                },
                timeout=timeout,
            )
            html = decode_body(rd)
            if dump_path and rd.status_code == 200:
                (dump_path / "electricdetail.html").write_text(html, encoding="utf-8")
            rows = extract_detail_comments(html) if rd.status_code == 200 else None
            if rows is not None:
                nonempty = [
                    x
                    for x in rows
                    if isinstance(x, dict) and str(x.get("ydl") or "").strip()
                ]
                result["detail"] = {
                    "month": detail_month,
                    "rows": rows,
                    "days_with_usage": nonempty,
                    "labels": {
                        "sj": "日期",
                        "ydl": "用电量(度)",
                        "ydje": "用电金额(元)",
                    },
                }
            else:
                result["errors"].append(
                    f"electricdetail 解析失败 status={rd.status_code}"
                )
        except Exception as exc:  # noqa: BLE001
            result["errors"].append(f"用电明细查询失败: {exc}")

    return result


def pretty_print_meter(result: dict[str, Any]) -> None:
    print("\n======== 长安大学电表查询 ========")
    print(f"学校: {result.get('area_name')} (id={result.get('area_id')})")
    print(f"表号: {result.get('meter')}")
    print(f"成功: {result.get('ok')}  status={result.get('status')}")
    b = result.get("balance") or {}
    if b:
        print(f"房间:       {b.get('room') or '-'}")
        print(f"预付费余额: {b.get('prepaid_yuan')} 元")
        print(f"总余额:     {b.get('total_yuan')} 元")
        if b.get("subsidy_yuan") not in (None, "", "0", "0.00"):
            print(f"补助余额:   {b.get('subsidy_yuan')} 元")
        print(f"累计电量:   {b.get('total_kwh')} 度")
        print(f"抄表时间:   {b.get('reading_time')}")
        print(f"电表状态:   {b.get('meter_status')}")
    bill = result.get("bill") or {}
    data = bill.get("data") if isinstance(bill, dict) else None
    if data:
        print(f"\n月账单月份: {bill.get('month')}")
        print(f"  期初示数: {data.get('qcdl')} 度")
        print(f"  期末示数: {data.get('qmdl')} 度")
        print(f"  用电量:   {data.get('ydl')} 度")
        print(f"  用电金额: {data.get('ydje')} 元")
    detail = result.get("detail") or {}
    days = detail.get("days_with_usage") if isinstance(detail, dict) else None
    if days is not None:
        total_rows = len(detail.get("rows") or [])
        print(
            f"\n日用电明细: {detail.get('month')} "
            f"（有数据 {len(days)} 天 / 共 {total_rows} 行）"
        )
        for row in days[:10]:
            print(f"  {row.get('sj')}: {row.get('ydl')} 度 / {row.get('ydje')} 元")
        if len(days) > 10:
            print(f"  ... 另有 {len(days) - 10} 天")
    if result.get("errors"):
        print("提示/错误:", result["errors"])
    print("==========================================\n")
