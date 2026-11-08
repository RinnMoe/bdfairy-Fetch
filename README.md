# 长安大学电表查询（bdfetch）

## 本仓库与上游原仓库的关系

| 项 | 说明 |
|----|------|
| 上游原仓库 | [guiguisocute/bdfairy-Fetch](https://github.com/guiguisocute/bdfairy-Fetch)（多校通用版，MIT） |
| 本仓库 | [RinnMoe/bdfairy-Fetch](https://github.com/RinnMoe/bdfairy-Fetch)（本 fork） |
| 关系 | 本仓库 fork 自上游；只保留长安大学（`areaId=65`）的链路与研究，不再维护其他学校/校区 |
| 上游定位 | 面向 `bd.bdfairy.cn` 的 55 所 full 学校通用 CLI/库，含 `meter_bill` / `cascade_ok` 等分层 |
| 上游探测时间 | `2026-07-28`（见上游 README） |
| 本仓库复测 | `2026-11-08`；只验证长安大学 |
| 同步策略 | 不自动跟随上游多校更新；上游内容仅作历史参考。需要其他学校请使用上游仓库 |
| 许可证 | 上游与本仓库均为 MIT（见 [LICENSE](LICENSE)） |

> 非官方工具，与北电 / 后勤宝 / 长安大学无隶属关系。仅供本人有权查询的数据与个人研究使用。

### 与上游的主要差异

| 维度 | 上游 | 本 fork |
|------|------|---------|
| 范围 | 55 所 full + 多校分层 | 仅长安大学（id=65） |
| 数据 | `supported_schools.json` | `data/changan.json` |
| CLI | `schools` + `--school` / `--school-name` / `--force` | `info` / `buildings` / `floors` / `rooms` / `room` / `meter` / `monitor` |
| 楼栋 | 根接口原样输出（116 条，含重复） | 按 `BuildingID` 去重（88 栋），带 `group` / `group_area` |
| 同名楼栋 | 取第一个匹配 | 必须 `--group` 消歧，或传 15 位楼栋 ID |
| 长安大学结论 | `cascade_ok`，绑房未解析出表号 | 已验证 `room`→表号、余额、月账单、日明细 |
| 文档 | 多校 README | 长安大学单校 README + `VERIFY.md` |

> 本仓库 README 取代上游 README 中与长安大学相关的旧结论；上游其他学校内容未复制到本仓库。

## 已验证能力

实测时间：`2026-11-08`。只针对长安大学，未复测其他学校。

| 能力 | 状态 | 说明 |
|------|:----:|------|
| 楼栋 `buildings` | ✅ | 静态快照 88 栋 / 502 层 / 18,089 间 / 6 个分组；刷新时根接口 116 条按 `BuildingID` 去重 |
| 楼层 `floors` | ✅ | 静态快照；例：`1号公寓` 4–5 层 |
| 房间 `rooms` | ✅ | 静态快照；例：`003` 组 `1号公寓` `1楼` 36 间 |
| 房间 → 表号 `room` | ✅ | 静态树解析房间；动态 `/login` + `/selectmeter` 取表号 |
| 余额 `meter_main` | ✅ | 预付费余额、补助余额、总余额、累计电量、闸位、抄表时间、计费类型 |
| 月账单 `electricbill` | ✅ | `qcdl` 期初、`qmdl` 期末、`ydl` 用电量、`ydje` 金额 |
| 日明细 `electricdetail` | ✅ | 每日 `sj`、`ydl`、`ydje` |
| 房间地址 | ❌ | 站点 `roomaddr` 返回 `undefined`，`balance.room` 为 `null` |

## 静态数据与动态数据

| 类型 | 数据 | 来源 | 更新方式 |
|------|------|------|----------|
| 静态 | 楼栋 / 楼层 / 房间树（88 栋 / 502 层 / 18,089 间） | `src/electricity/data/changan_tree.json` 本地快照 | 仅 `bdfetch buildings --refresh` |
| 动态 | 绑房、表号、余额、月账单、日明细 | `/login`、`/selectmeter`、`/meter_main`、`/electricbill`、`/electricdetail` | 每次查询实时请求 |

楼栋/房间结构几乎不变，默认命令（`buildings` / `floors` / `rooms` / `room` 的路径解析）不访问 `/getB`；只有显式 `--refresh` 才重新抓取并覆盖快照。这样避免每次查询几百次 `/getB` 请求，也避免站点限流。全树刷新一次约数分钟，生成约 2.5MB JSON；只在结构变化时执行。

## 安装

要求 Python >= 3.10；运行依赖只有 `requests`。

### uv（推荐）

```bash
uv venv
uv pip install -e .
```

### pip

```bash
python -m venv .venv
# Windows:  .\.venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -e .
```

依赖只有 `requests`。`bdfetch` 安装在虚拟环境的 `Scripts` / `bin` 里：

```powershell
# 激活后
bdfetch --help
# 或直接用 uv 代跑
uv run bdfetch --help
# 或写相对路径
.\.venv\Scripts\bdfetch.exe --help
```

## 快速开始

```bash
# 长安大学能力、分组、代号规则
bdfetch info

# 楼栋（输出含 group / group_area，按 BuildingID 去重）
bdfetch buildings

# 楼层 / 房间（同名楼栋必须用 --group 消歧）
bdfetch floors --building 1号公寓 --group 003
bdfetch rooms  --building 1号公寓 --group 003 --floor 1楼

# 房间 → 表号
bdfetch room --building 1号公寓 --group 003 --floor 1楼 --room <房间> --json

# 表号 → 余额 / 月账单 / 日明细
bdfetch meter --meter <表号> --detail --no-dump --json
```

退出码：`0` 成功 · `1` 参数错误 · `2` 无数据 / 查询失败。

## CLI 一览

```text
bdfetch <子命令> [选项]

info       长安大学能力、分组与代号规则
buildings  列出楼栋（按 BuildingID 去重）
floors     列出某楼栋的楼层
rooms      列出某层的房间
room       房间 → 表号（可再查余额）
meter      表号 → 余额/月账单/日明细
monitor    短时轮询余额
```

### 全局参数

| 参数 | 说明 |
|------|------|
| `--base` | 站点根 URL，默认 `http://bd.bdfairy.cn` |
| `--timeout` | 单请求超时，默认 20s |

### `buildings`

```bash
bdfetch buildings                  # 读本地静态快照，不访问站点
bdfetch buildings --refresh        # 显式刷新：访问 /getB 全树，耗时较长
bdfetch buildings --out output/buildings.json
```

输出字段：`name`、`id`、`group`（3 位分组）、`group_area`（观测到的区域名）、`floor_count`、`room_count`，以及 `tree.updated_at` / `tree.counts` 元信息。刷新时会按 `BuildingID` 去重。

### `floors` / `rooms`

```bash
bdfetch floors --building 1号公寓 --group 003
bdfetch floors --building 001000003000001          # 也可以直接传 15 位楼栋 ID
bdfetch rooms  --building 1号公寓 --group 003 --floor 1楼
```

`--group` 用于同名楼栋消歧（如 `1号公寓` 同时出现在 `003/005/006/007` 组）。不传且名称不唯一时，会报错并列出候选。楼层/房间均来自静态快照，不访问站点。

### `room`

```bash
bdfetch room --building 1号公寓 --group 003 --floor 1楼 --room <房间> --json
bdfetch room --building 1号公寓 --group 003 --floor 1楼 --room <房间> --with-balance
bdfetch room --building 1号公寓 --group 003 --floor 1楼 --scan-floor --out output/room_meters.json
bdfetch room --building 1号公寓 --group 003 --floor 1楼 --scan-floor --resume --out output/room_meters.json
```

- `--scan-floor` 会跳过占位房间「充值前请确认房间」，避免浪费绑房次数。
- `--resume` 读取已有 JSON，跳过已扫到的房间。
- 楼栋/楼层/房间路径来自静态快照；只有 `/login` + `/selectmeter` 是动态请求。
- **一个房间可能有多个表**（如空调 / 照明）：`meters[]` 是全部表号，`meter_rows[]` 含 `PipLineName`（如 `...(空调)` / `...(照明)`）、`EqptTypeName` 等；`meter` 只是第一个。`--with-balance` 会逐个查询所有表。
- `--scan-floor` 导出的记录在多个表时会带 `meters[]`，不会只保留第一个表。

`--json` 返回的主要字段：

| 字段 | 说明 |
|------|------|
| `ok` | 是否解析到表号 |
| `meter` / `meters[]` | 第一个表号 / 全部表号 |
| `meter_rows[]` | 设备明细：`comAddress`、`PipLineName`（空调/照明）、`EqptTypeName`、`EnergyTypeName` 等 |
| `path.group` / `path.group_area` | 楼栋分组 / 观测区域 |
| `path.building` / `path.floor` / `path.room` | 实际匹配到的级联路径 |
| `building_info` / `building_id` | `POST /login` 使用的 buildingInfo / 房间 ID |
| `page` | 绑房后页面（`selectmeter`） |

### `meter`

```bash
bdfetch meter --meter <表号>
bdfetch meter --meter <表号> --detail
bdfetch meter --meter <表号> --month 2026-10 --detail --json
bdfetch meter --meter <表号> --no-bill --no-dump --json
```

默认包含月账单；`--no-bill` 跳过。`--detail` 额外拉日明细。

`--json` 返回的主要字段：

| 字段 | 说明 |
|------|------|
| `ok` / `status` | `valid` / `empty` / `error` |
| `balance.prepaid_yuan` / `subsidy_yuan` / `total_yuan` | 预付费 / 补助 / 总余额 |
| `balance.total_kwh` / `meter_status` / `reading_time` | 累计电量 / 闸位 / 抄表时间 |
| `balance.room` | 站点未返回，通常为 `null` |
| `bill.month` / `bill.data.qcdl` / `qmdl` / `ydl` / `ydje` | 月账单 |
| `detail.month` / `detail.rows[]` | 日明细；`sj` 为 `YYYYMMDD`，含 `ydl` / `ydje` |
| `errors[]` | 部分接口失败信息 |

### `monitor`

```bash
bdfetch monitor --meter <表号> --minutes 15 --interval 30
```

## 长安大学代号规则

长安大学的楼栋/楼层/房间代号是**定长拼接**，没有分隔符：

```text
001000 | 003 | 000001 | 000001 | 001
 root   group  building  floor   room
  6       3       6        6       3
```

| 段 | 长度 | 示例 | 语义 |
|----|-----:|------|------|
| `root` | 6 | `001000` | 校区根节点 |
| `group` | 3 | `003` | 楼栋分组，本身可作为 `bID` 查询 |
| `building` | 6 | `000001` | 组内楼栋序号 |
| `floor` | 6 | `000001` | 楼层序号（1楼=`000001`） |
| `room` | 3 | `001` | 楼层内房间序号，**不是房号** |

### 分组对应（观测）

| group | 区域 | 唯一楼栋 | 代表楼栋 |
|------:|------|---------:|----------|
| `003` | 北院 | 13 | 1–12号公寓、西门科技服务1号公寓 |
| `004` | 东院 | 5 | 3、4、5、8、9号公寓 |
| `005` | 西院 | 6 | 1、2、3、4、5、7号公寓 |
| `006` | 渭水校区 | 26 | 1–22号公寓、21A/21B、23A/23B、综合楼 |
| `007` | 渭水校区 | 24 | 1–22号公寓、21A/21B、综合楼 |
| `008` | 混合 | 14 | 渭水修建中心、北院花园公寓、南院、东院青年公寓、西院平房等 |

`group` 不是官方区域枚举，只是楼栋分组/批次；`006/007` 都显示渭水校区，`008` 混合多个区域。准确位置以楼名/房间名为准。

### 同一校区多个代码怎么选

| 代码 | 区域 | 状态 | 说明 / 建议 |
|-----:|------|------|-------------|
| `003` | 北院 | 独立区域树 | 北院楼栋用 `003` |
| `004` | 东院 | 独立区域树 | 东院楼栋用 `004` |
| `005` | 西院 | 独立区域树 | 西院楼栋用 `005` |
| `006` | 渭水校区 | **已验证主树** | 渭水优先用 `006`；含 23A/23B；实测 406/101 有表号 |
| `007` | 渭水校区 | **疑似重复/旧树** | 与 `006` 高度重叠、缺 23A/23B；实测 1号/2号公寓 101、1号公寓 406 无表号；仅作 `006` 查不到时的兜底 |
| `008` | 混合 | 跨区域零散组 | 渭水修建中心、北院花园公寓、南院、东院青年公寓、西院平房等专用，不是渭水校区别名 |

判断某个房间到底用哪个代码，直接看 `room` 的 `ok` / `meters`：

```bash
bdfetch room --building 1号公寓 --group 006 --floor 4楼 --room 渭水校区1号公寓4楼406 --json
bdfetch room --building 1号公寓 --group 007 --floor 4楼 --room 渭水校区1号公寓4楼406 --json
# ok=true 且 meters 非空 → 该代码有效
```

- 同名楼栋不一定是重复：`003/004/005` 的“1号公寓”分别是北院/东院/西院的不同物理楼栋。
- `006/007` 才是真正的同名重叠树；当前结论是 `006` 有效、`007` 疑似重复/旧树。
- `008` 只用于它列出的跨区域楼栋，不要拿 `008` 去查渭水 1号公寓。

### 序号规则

- **楼栋序号**：组内顺序，不是楼号。<br>
  例：`004` 组 `3号公寓=000001`、`4号=000002`、`5号=000003`、`8号=000004`、`9号=000005`。
- **楼层序号**：等于楼层序号。<br>
  例：`1楼=000001`、`2楼=000002`、`3楼=000003`。
- **房间序号**：楼层内 1-based 顺序，不是房号。<br>
  例：`003` 组 1号公寓：101→`001`、102→`002`、103→`003`、104→`004`、**106→`005`**（105 缺失不影响序号）；最后 `公寓门卫=035`、占位房间 `充值前请确认房间=036`。
- **特殊房间**：厨房、门卫、占位项继续占用序号；占位项可能显示在最前但序号最大（如 `036`）。

### 示例拆分

```text
001000003000001000001001
001000 | 003 | 000001 | 000001 | 001
root    北院  1号公寓   1楼      第1间（101）

001000006000001000001001
001000 | 006 | 000001 | 000001 | 001
root    渭水  1号公寓   1楼      第1间（101）

001000003000001000001036
001000 | 003 | 000001 | 000001 | 036
root    北院  1号公寓   1楼      占位「充值前请确认房间」（无表号）
```

解析代码：

```python
from electricity import split_id, describe_id

split_id("001000003000001000001001")
# {'root': '001000', 'group': '003', 'building': '000001',
#  'floor': '000001', 'room': '001'}

describe_id("001000003000001000001001")
# 'root=001000 / group=003 / building=000001 / floor=000001 / room=001'
```

## HTTP 链路

```text
GET  /?id=65
POST /selectarea        {areaId, areaName}
POST /getB              {bID: root|group|building}   → floor 数组（楼栋）   # 仅 --refresh
POST /getB              {fID: building_id}          → room 数组（楼层）     # 仅 --refresh
POST /getB              {rID1: floor_id}            → room1 数组（房间）    # 仅 --refresh
POST /login             {buildingInfo, buildingID}  → href=selectmeter
GET  /selectmeter                                    内嵌 data=ref(JSON.parse(...))
POST /selectmeter       {comAddress, hidType:"电表"}  → url=/meter_main
GET  /meter_main                                     余额
GET  /electricbill                                   月账单
POST /electricdetail    {month, comAddress}          日明细（必须 POST）
POST /phonejcbd                                      解绑（band=1 时）
```

`/getB` 只在 `bdfetch buildings --refresh` 刷新静态树时使用；默认查询不访问。响应字段名统一是 `BuildingName` / `BuildingID`；层级由请求键和数组名决定。高层查询还会附带 `room` / `room1` 预览（第一栋的楼层/第一层的房间），枚举时不要误当成完整列表。

## 站点行为与坑

1. **绑房状态 `band=1`**：绑定过房间后 `selectarea` 返回 `band=1`，此时 `/getB` 返回 500。程序会自动 `POST /phonejcbd` 解绑后重试；页面提示换房次数上限 4 次，批量扫描请控制频率。
2. **占位房间**：部分楼栋 `1楼` 首个房间是「充值前请确认房间」，`JSON.parse('[]')` 无表号；`--scan-floor` 会跳过。
3. **OAuth 跳转**：非微信 UA 访问 `GET /?id=65` 会 302 到 `open.weixin.qq.com`；本项目请求已带 MicroMessenger UA，余额/账单/明细/级联链路不受影响。
4. **楼栋重复**：刷新时根接口 `bID=001000` 返回 116 条，其中 88 个唯一 `BuildingID`；刷新逻辑已去重。按 group 查询也会去重（13/5/6/26/24/14）。
5. **楼名不唯一**：`1号公寓` 同时出现在 `003/005/006/007` 组；请用 `--group` 或 15 位楼栋 ID。
6. **房间序号不是房号**：`room` 段是楼层内顺序号；106 可能对应 `005`。
7. **房间地址**：`roomaddr` 返回 `undefined`，`balance.room` 为 `null`。
8. **静态快照可能过期**：站点新增/调整楼栋房间后，`buildings` / `floors` / `rooms` / `room` 可能找不到；运行 `bdfetch buildings --refresh` 更新快照。
9. **一房多表**：部分房间有空调 / 照明两个表；不要只取 `meter`，请看 `meters[]` / `meter_rows[]`，或直接用 `--with-balance` 逐个查询。

## 故障排查

| 现象 | 原因 | 处理 |
|------|------|------|
| `bdfetch` 不是内部或外部命令 | 未激活 venv / 不在 PATH | `.\.venv\Scripts\Activate.ps1`，或 `uv run bdfetch` |
| `楼栋不唯一` | 同名楼栋跨分组 | 加 `--group 003`，或传 15 位楼栋 ID |
| `/getB` 500 / 级联失败 | 已绑房 `band=1` | 程序会自动 `/phonejcbd`；仍失败则稍后重试，避免频繁换房 |
| `缺少静态楼栋快照` | 未生成 / 被删除 | `bdfetch buildings --refresh` |
| `找不到房间/楼层` | 静态快照过期 | 先 `bdfetch buildings --refresh`，再确认名称 |
| `GET /?id=65` 302 OAuth | 非微信 UA | 用本项目请求（已带 MicroMessenger UA），不要用普通浏览器直接调 API |
| 房间存在但无表号 | 占位/空置/锁房 | 换真实房间；`--scan-floor` 会跳过「充值前请确认房间」 |
| `balance.room` 为 null | 站点 `roomaddr=undefined` | 正常现象，用房间级联结果代替 |
| 找不到楼层 | 楼层名不是 `1楼` 格式 | 先 `bdfetch floors` / `bdfetch rooms` 看实际名称 |

## 作为库使用

```python
from electricity import (
    AREA_ID, AREA_NAME, CAMPUS_ROOT,
    query_meter, query_room,
    list_buildings, list_floors, list_rooms, load_tree,
    split_id, describe_id,
)

print(AREA_ID, AREA_NAME, CAMPUS_ROOT)   # 65 长安大学 001000

for b in list_buildings():
    print(b["group_area"], b["name"], b["id"], b["room_count"])

floors = list_floors("1号公寓", group="003")
rooms = list_rooms("1号公寓", "1楼", group="003")
print(len(floors["floors"]), len(rooms["rooms"]))

r = query_meter("<表号>", include_detail=True)
print(r["balance"]["total_yuan"])

room = query_room(
    building="1号公寓",
    group="003",
    floor="1楼",
    room="<房间>",
)
print(room["meter"])
for row in room["meter_rows"]:
    print(row["comAddress"], row.get("PipLineName"))
```

`list_buildings()` / `list_floors()` / `list_rooms()` / `load_tree()` 只读本地静态快照，不访问网络；`query_meter()` / `query_room()` 默认就是长安大学，无需再传学校参数。需要更新静态树时调用 `refresh_tree()`（会访问 `/getB`，耗时较长），或运行 `bdfetch buildings --refresh`。

## 项目结构

```text
.
├── README.md
├── VERIFY.md                 # 环境与长安大学实测记录
├── pyproject.toml
├── requirements.txt          # requests
├── config.example.env
├── LICENSE
├── tests/test_offline.py     # 离线自检（unittest）
└── src/electricity/
    ├── __init__.py           # 公开 API
    ├── __main__.py           # python -m electricity
    ├── changan.py            # 长安大学常量、档案、代号拆分
    ├── tree.py               # 静态楼栋树：快照加载/查询/刷新
    ├── cli.py                # bdfetch 入口
    ├── meter.py              # 表号直查（动态）
    ├── room.py               # 房间→表号（静态树 + 动态绑房）
    ├── session.py            # 匿名会话 / 选校 / 解绑
    ├── client.py             # UA 与站点常量
    ├── util.py
    └── data/
        ├── changan.json      # 能力、分组、代号规则、验证备注
        └── changan_tree.json # 楼栋/楼层/房间静态快照
```

## 开发与验证

要求 Python >= 3.10；运行依赖只有 `requests`。

```bash
uv venv
uv pip install -e .
uv run python -m unittest discover -s tests -v
uv build
```

完整的环境、实测命令、结果与限制见 [VERIFY.md](./VERIFY.md)。

## 文档索引

| 文档 | 内容 |
|------|------|
| [README.md](README.md) | 本文件：上游关系、安装、CLI、代号规则、HTTP、坑与排查 |
| [VERIFY.md](VERIFY.md) | 环境、重构说明、19 项离线自检、长安大学实测与证据 |
| [src/electricity/data/changan.json](src/electricity/data/changan.json) | 能力、计数、分组、代号规则、验证备注（机器可读） |
| [src/electricity/data/changan_tree.json](src/electricity/data/changan_tree.json) | 楼栋/楼层/房间静态快照（默认查询的数据源） |
| [src/electricity/changan.py](src/electricity/changan.py) | 常量、档案加载、`split_id` / `describe_id` |
| [src/electricity/tree.py](src/electricity/tree.py) | 静态树加载/查询/显式刷新 |
| [tests/test_offline.py](tests/test_offline.py) | 离线自检（档案/代号/CLI/公开 API） |
| [config.example.env](config.example.env) | 配置占位（长安大学查询无需配置） |
| [LICENSE](LICENSE) | MIT 许可证 |

## 隐私与免责

1. 静态快照包含站点公开的楼栋/楼层/房间名称与 ID（用于离线解析）；不包含表号、余额金额、个人绑定信息。`output/` 与探针文件已被 `.gitignore` 忽略。
2. 请只查询本人有权查询的数据，勿公开真实表号与房间信息。
3. 接口以站点为准，可能变更；本项目只覆盖长安大学，不保证其他学校可用。
4. 使用风险自负，请遵守学校与服务方相关规定。

## 许可证

MIT — 见 [LICENSE](./LICENSE)。
