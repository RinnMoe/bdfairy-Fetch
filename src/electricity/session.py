"""长安大学匿名会话：入口 Cookie + 选校 + 必要时解绑（无需微信登录）。"""

from __future__ import annotations

import json
from typing import Any

import requests

from .changan import AREA_ID, AREA_NAME
from .client import DEFAULT_BASE, WECHAT_UA


def decode_body(r: requests.Response) -> str:
    """服务端偶发非 UTF-8，多编码回退。"""
    raw = r.content or b""
    if not raw:
        return ""
    for enc in ("utf-8-sig", "utf-8", "gb18030", "gbk", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def jload(r: requests.Response) -> Any:
    text = decode_body(r).strip()
    if not text:
        raise ValueError("empty response body")
    return json.loads(text)


def headers_json(base: str, referer: str) -> dict[str, str]:
    ref = referer if referer.startswith("http") else base.rstrip("/") + referer
    return {
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "Origin": base.rstrip("/"),
        "Referer": ref,
    }


def new_session(*, timeout: float = 20.0) -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": WECHAT_UA,
            "X-Requested-With": "com.tencent.mm",
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;"
                "q=0.9,*/*;q=0.8"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
    )
    # timeout 由各请求单独传入；此处仅建会话
    _ = timeout
    return s


def selectarea(
    s: requests.Session,
    *,
    area_id: str = AREA_ID,
    area_name: str = AREA_NAME,
    base: str = DEFAULT_BASE,
    timeout: float = 20.0,
) -> dict[str, Any]:
    base = base.rstrip("/")
    s.get(f"{base}/?id={area_id}", allow_redirects=False, timeout=timeout)
    r = s.post(
        f"{base}/selectarea",
        json={"areaId": str(area_id), "areaName": area_name},
        headers=headers_json(base, "/selectArea"),
        timeout=timeout,
    )
    try:
        return jload(r)
    except Exception:
        return {"_error": True, "text": decode_body(r)[:200], "status": r.status_code}


def maybe_unbind(
    s: requests.Session,
    sa: dict[str, Any],
    *,
    area_id: str = AREA_ID,
    area_name: str = AREA_NAME,
    base: str = DEFAULT_BASE,
    timeout: float = 20.0,
) -> tuple[requests.Session, dict[str, Any]]:
    """
    已绑房间时 meter_main 常 500/errorApp。
    解绑后换新会话再选校。
    """
    base = base.rstrip("/")
    bound = str(sa.get("band")) == "1" or sa.get("data") in (
        "selectmeter",
        "selectPhoneMeter",
        "meter_main",
    )
    if not bound:
        return s, sa

    try:
        s.post(
            f"{base}/phonejcbd",
            json={},
            headers=headers_json(base, "/selectPhoneMeter"),
            timeout=timeout,
        )
    except requests.RequestException:
        pass

    s2 = new_session()
    sa2 = selectarea(
        s2, area_id=area_id, area_name=area_name, base=base, timeout=timeout
    )
    if isinstance(sa2, dict):
        sa2 = {**sa2, "_unbound": True}
    return s2, sa2


def bootstrap_area(
    *,
    area_id: str = AREA_ID,
    area_name: str = AREA_NAME,
    base: str = DEFAULT_BASE,
    timeout: float = 20.0,
    unbind_if_bound: bool = True,
) -> tuple[requests.Session, dict[str, Any]]:
    """匿名入口 + 选校（默认已绑则解绑）。"""
    s = new_session()
    sa = selectarea(
        s, area_id=area_id, area_name=area_name, base=base, timeout=timeout
    )
    if unbind_if_bound and isinstance(sa, dict):
        s, sa = maybe_unbind(
            s,
            sa,
            area_id=area_id,
            area_name=area_name,
            base=base,
            timeout=timeout,
        )
    return s, sa
