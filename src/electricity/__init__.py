"""长安大学（bd.bdfairy.cn areaId=65）电表查询公开 API。

只依赖 ``requests``；楼栋/楼层/房间、表号、余额、账单、日明细均走免微信 OAuth 链路。

典型用法::

    from electricity import query_meter, query_room, list_buildings

    for b in list_buildings():
        print(b["group_area"], b["name"], b["id"])

    r = query_meter("<表号>", include_detail=True)
    print(r["balance"]["total_yuan"])

    room = query_room(
        building="1号公寓",
        group="003",
        floor="1楼",
        room="<房间>",
    )
    print(room["meter"])
"""

from __future__ import annotations

from .changan import (
    AREA_ID,
    AREA_NAME,
    CAMPUS_ROOT,
    describe_id,
    get_school,
    group_areas,
    load_profile,
    split_id,
)
from .client import DEFAULT_BASE
from .meter import pretty_print_meter, query_meter
from .room import (
    list_buildings,
    list_floors,
    list_rooms,
    query_room,
    scan_floor,
)

__version__ = "1.0.0"

__all__ = [
    "__version__",
    "AREA_ID",
    "AREA_NAME",
    "CAMPUS_ROOT",
    "DEFAULT_BASE",
    "get_school",
    "load_profile",
    "group_areas",
    "split_id",
    "describe_id",
    "query_meter",
    "pretty_print_meter",
    "query_room",
    "scan_floor",
    "list_buildings",
    "list_floors",
    "list_rooms",
]
