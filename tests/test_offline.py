"""离线自检：长安大学档案、代号规则、表号解析、CLI 参数。

运行::

    .venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""

from __future__ import annotations

import contextlib
import io
import unittest

import electricity
from electricity import (
    AREA_ID,
    AREA_NAME,
    CAMPUS_ROOT,
    describe_id,
    get_school,
    group_areas,
    list_buildings,
    list_floors,
    list_rooms,
    load_profile,
    load_tree,
    resolve_room,
    split_id,
    tree_meta,
)
from electricity.cli import build_parser
from electricity.room import export_record, extract_meter_rows, extract_meters


class ProfileTests(unittest.TestCase):
    def test_school_identity(self) -> None:
        school = get_school()
        self.assertEqual(school["id"], "65")
        self.assertEqual(school["name"], "长安大学")
        self.assertEqual(school["campus_root"], "001000")
        self.assertEqual(school["tier"], "full")

    def test_constants(self) -> None:
        self.assertEqual((AREA_ID, AREA_NAME, CAMPUS_ROOT), ("65", "长安大学", "001000"))

    def test_capabilities(self) -> None:
        caps = get_school()["capabilities"]
        for key in (
            "buildings",
            "floors",
            "rooms",
            "room_to_meter",
            "balance",
            "bill",
            "detail",
        ):
            self.assertTrue(caps[key], key)

    def test_counts(self) -> None:
        counts = get_school()["counts"]
        self.assertEqual(counts["building_entries"], 116)
        self.assertEqual(counts["building_unique"], 88)
        self.assertEqual(counts["groups"], 6)

    def test_group_areas(self) -> None:
        areas = group_areas()
        self.assertEqual(areas["003"], "北院")
        self.assertEqual(areas["004"], "东院")
        self.assertEqual(areas["005"], "西院")
        self.assertEqual(areas["006"], "渭水校区")
        self.assertEqual(areas["007"], "渭水校区")
        self.assertEqual(areas["008"], "混合")

    def test_group_statuses(self) -> None:
        groups = {g["code"]: g for g in load_profile()["groups"]}
        self.assertEqual(groups["006"]["status"], "verified")
        self.assertEqual(groups["007"]["status"], "duplicate_suspect")
        self.assertEqual(groups["008"]["status"], "mixed")

    def test_id_rule_profile(self) -> None:
        widths = load_profile()["id_rule"]["widths"]
        self.assertEqual(
            widths,
            {
                "root": 6,
                "group": 3,
                "building": 6,
                "floor": 6,
                "room": 3,
            },
        )


class IdRuleTests(unittest.TestCase):
    def test_room_id_split(self) -> None:
        self.assertEqual(
            split_id("001000003000001000001001"),
            {
                "root": "001000",
                "group": "003",
                "building": "000001",
                "floor": "000001",
                "room": "001",
            },
        )

    def test_building_id_split(self) -> None:
        self.assertEqual(
            split_id("001000004000001"),
            {"root": "001000", "group": "004", "building": "000001"},
        )

    def test_floor_id_split(self) -> None:
        self.assertEqual(
            split_id("001000006000001000002"),
            {
                "root": "001000",
                "group": "006",
                "building": "000001",
                "floor": "000002",
            },
        )

    def test_short_group_id(self) -> None:
        self.assertEqual(
            split_id("001000003"), {"root": "001000", "group": "003"}
        )

    def test_describe_id(self) -> None:
        text = describe_id("001000003000001000001001")
        for part in ("root=001000", "group=003", "building=000001", "floor=000001", "room=001"):
            self.assertIn(part, text)


class TreeSnapshotTests(unittest.TestCase):
    def test_snapshot_available(self) -> None:
        meta = tree_meta()
        self.assertTrue(meta["available"])
        self.assertIsNotNone(meta["updated_at"])
        self.assertEqual(meta["counts"]["buildings"], 88)
        self.assertGreater(meta["counts"]["floors"], 0)
        self.assertGreater(meta["counts"]["rooms"], 0)

    def test_buildings_from_snapshot(self) -> None:
        rows = list_buildings()
        self.assertEqual(len(rows), 88)
        self.assertEqual(len(list_buildings(group="004")), 5)
        b = next(
            x for x in rows if x["group"] == "003" and x["name"] == "1号公寓"
        )
        self.assertEqual(b["floor_count"], 4)
        self.assertEqual(b["room_count"], 144)

    def test_floors_and_rooms_from_snapshot(self) -> None:
        f = list_floors("1号公寓", group="003")
        self.assertEqual(
            [x["name"] for x in f["floors"]],
            ["1楼", "2楼", "3楼", "4楼"],
        )
        r = list_rooms("1号公寓", "1楼", group="003")
        self.assertEqual(len(r["rooms"]), 36)
        self.assertEqual(r["rooms"][0]["name"], "充值前请确认房间")

    def test_resolve_room_from_snapshot(self) -> None:
        path = resolve_room("1号公寓", "1楼", "101", group="003")
        self.assertIn("101", path["room"]["name"])
        self.assertTrue(
            path["room"]["id"].startswith("001000003000001000001")
        )
        self.assertEqual(load_tree()["counts"]["buildings"], 88)


class MeterExtractTests(unittest.TestCase):
    def test_vue_json_parse_payload(self) -> None:
        # 长安大学 /selectmeter 页面的真实数据形态
        html = (
            "<script>const data = ref(JSON.parse("
            "'[{\"comAddress\":\"123456789012\",\"BuildingName\":\"示例房间\"}]'"
            "))</script>"
        )
        self.assertEqual(extract_meters(html), ["123456789012"])

    def test_placeholder_room_has_no_meter(self) -> None:
        html = "<script>const data = ref(JSON.parse('[]'))</script>"
        self.assertEqual(extract_meters(html), [])

    def test_two_meters_with_labels(self) -> None:
        html = (
            "<script>const data = ref(JSON.parse("
            "'[{\"comAddress\":\"111111111111\",\"PipLineName\":\"示例406(空调)\"},"
            "{\"comAddress\":\"222222222222\",\"PipLineName\":\"示例406(照明)\"}]'"
            "))</script>"
        )
        rows = extract_meter_rows(html)
        self.assertEqual(
            [r["comAddress"] for r in rows],
            ["111111111111", "222222222222"],
        )
        self.assertEqual(
            [r["PipLineName"] for r in rows],
            ["示例406(空调)", "示例406(照明)"],
        )
        self.assertEqual(
            extract_meters(html), ["111111111111", "222222222222"]
        )

    def test_export_record_keeps_multi_meters(self) -> None:
        rec = export_record(
            building="示例楼",
            floor="4楼",
            room="示例406",
            meter="111111111111",
            meters=["111111111111", "222222222222"],
        )
        self.assertEqual(rec["meter"], "111111111111")
        self.assertEqual(rec["meters"], ["111111111111", "222222222222"])


class CliParserTests(unittest.TestCase):
    def test_info(self) -> None:
        args = build_parser().parse_args(["info"])
        self.assertEqual(args.command, "info")

    def test_floors_with_group(self) -> None:
        args = build_parser().parse_args(
            ["floors", "--building", "1号公寓", "--group", "003"]
        )
        self.assertEqual(args.command, "floors")
        self.assertEqual(args.group, "003")

    def test_room(self) -> None:
        args = build_parser().parse_args(
            [
                "room",
                "--building",
                "1号公寓",
                "--group",
                "003",
                "--floor",
                "1楼",
                "--room",
                "101",
                "--json",
            ]
        )
        self.assertEqual(args.command, "room")
        self.assertEqual(args.building, "1号公寓")
        self.assertTrue(args.json)

    def test_buildings_refresh(self) -> None:
        args = build_parser().parse_args(["buildings", "--refresh"])
        self.assertEqual(args.command, "buildings")
        self.assertTrue(args.refresh)

    def test_meter(self) -> None:
        args = build_parser().parse_args(["meter", "--meter", "123456789012"])
        self.assertEqual(args.command, "meter")
        self.assertEqual(args.meter, "123456789012")

    def test_schools_command_removed(self) -> None:
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            build_parser().parse_args(["schools"])


class PublicApiTests(unittest.TestCase):
    def test_version_and_exports(self) -> None:
        self.assertEqual(electricity.__version__, "1.0.0")
        for name in (
            "query_meter",
            "query_room",
            "list_buildings",
            "list_floors",
            "list_rooms",
            "load_tree",
            "resolve_room",
            "get_school",
            "split_id",
        ):
            self.assertTrue(callable(getattr(electricity, name)))


if __name__ == "__main__":
    unittest.main()
