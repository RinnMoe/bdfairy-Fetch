# bdfairy-Fetch

电精灵服务号（[bd.bdfairy.cn](http://bd.bdfairy.cn)）**多校电表查询** Python 库 + CLI。

- **55 所**探测为 `full`（表号 + 余额）；另有 **meter_bill / cascade_ok** 等有限支持校区（见下文）
- **无需微信登录 / OAuth**（匿名 `connect.sid` 即可）
- 表号直查余额 / 月账单 / 日用电明细
- 房间级联：楼栋 → 楼层 → 房间 → 表号
- 统一命令行：`bdfetch`

> 非官方工具，与北电 / 后勤宝及各高校无隶属关系。仅供个人宿舍查询与研究，使用前请获取充分授权

**关于微信 OAuth：** 本工具**不依赖、也不提供**可用的微信登录方案。余额 / 账单 / 日明细 / 房间查表号均走免登录链路。充值流水等极少数接口理论上要微信会话，只能在微信内操作时用 Fiddler / mitmproxy 等**实时抓包**拷请求头——本项目不覆盖该能力。

---

## 安装

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
# 或: pip install -r requirements.txt && pip install -e .
```

### 安装后如何调用 `bdfetch`

`bdfetch` 装在**虚拟环境**的 `Scripts` 里，例如：

```text
.venv\Scripts\bdfetch.exe
```

**没有激活 venv 时，直接敲 `bdfetch` 会报「无法识别 / not recognized」**——命令不在系统 PATH 里

任选一种方式：

```bash
# 方式 A：激活虚拟环境后再用（PowerShell）
.\.venv\Scripts\activate
bdfetch --help

# 方式 B：不激活，用 uv 代跑（推荐，少踩坑）
uv run bdfetch --help
uv run bdfetch schools

# 方式 C：写相对路径
.\.venv\Scripts\bdfetch.exe --help

# 方式 D：模块入口（同样要在 venv 内，或 uv run）
uv run python -m electricity --help
```

macOS / Linux：

```bash
source .venv/bin/activate
bdfetch --help
# 或
uv run bdfetch --help
```

提示符出现 `(.venv)`，且 `Get-Command bdfetch`（PowerShell）/ `which bdfetch` 指向本项目下的 `.venv`，即配置正确。

---

## 30 秒上手

下面示例默认你已 **`activate` 过 venv**，或在命令前加 **`uv run`**（如 `uv run bdfetch schools`）。

```bash
# 支持哪些学校
bdfetch schools
bdfetch schools --query 江西

# 表号查电费（江西师范大学 id=83）
bdfetch meter --school 83 --meter <表号>

# 带日明细 + JSON
bdfetch meter --school 80 --meter <表号> --detail --json

# 房间 → 表号 → 余额
bdfetch buildings --school 83
bdfetch room --school 83 --building <楼栋> --floor <楼层> --room <房间> --with-balance
```

**退出码：`0` 成功 · `1` 参数错误 · `2` 无数据 / 查询失败。**

## CLI 一览

```text
bdfetch <子命令> [选项]

schools      列出 55 所 full 学校
info         单校能力与推荐命令
meter        表号 → 余额 / 月账单 / 日明细
buildings    列出楼栋
floors       列出楼层
rooms        列出房间
room         房间 → 表号（可扫层）
monitor      短时轮询余额
```

### 全局常用参数

| 参数 | 说明 |
|------|------|
| `--school` / `--school-id` | 学校数字 id |
| `--school-name` | 校名（可模糊） |
| `--base` | 默认 `http://bd.bdfairy.cn` |
| `--timeout` | 单请求超时，默认 20s |
| `--out` | 结果 JSON 路径 |
| `--json` | 只打 JSON |

### `schools`

```bash
bdfetch schools
bdfetch schools -q 师范 --verbose
bdfetch schools --only-bill --json
```

| 列 | 含义 |
|----|------|
| ID | `areaId`，传给 `--school` |
| 余额 | `meter_main` 可读 |
| 账单 | 月账单（部分校为 N，余额仍可用） |
| 明细 | 日明细 `electricdetail` |

学校清单内置于包：`electricity/data/supported_schools.json`。

### `meter`（核心）

```bash
bdfetch meter --school 83 --meter <表号>
bdfetch meter --school 83 --meter <表号> --month 2026-06 --detail
bdfetch meter --school 83 --meter <表号> --no-bill --no-dump --json
```

| 参数 | 说明 |
|------|------|
| `--meter` / `-m` | 表号 `comAddress` |
| `--month` | `YYYY-MM` |
| `--detail` | 拉日用电明细 |
| `--no-bill` | 跳过月账单 |
| `--no-dump` | 不写 HTML 调试文件 |
| `--force` | 非 55 所列表内 id 不警告 |

**JSON 字段摘要：**

```json
{
  "ok": true,
  "status": "valid",
  "balance": {
    "prepaid_yuan": "17.07",
    "total_yuan": "17.07",
    "total_kwh": "3399.70",
    "meter_status": "…合闸…",
    "reading_time": "2026-07-29 18:28:08",
    "room": null
  },
  "bill": {
    "month": "2026-07",
    "data": { "qcdl": "…", "qmdl": "…", "ydl": "…", "ydje": "…" }
  },
  "detail": {
    "month": "2026-07",
    "days_with_usage": [{ "sj": "2026-07-01", "ydl": "1.2", "ydje": "0.74" }]
  }
}
```

`status`：`valid` | `empty`（空号）| `error`（可重试）。

### `buildings` / `floors` / `rooms`

```bash
bdfetch buildings --school 83
bdfetch floors --school 83 --building <楼栋>
bdfetch rooms  --school 83 --building <楼栋> --floor <楼层>
bdfetch buildings --school 54 --campus-id 001000001
```

### `room`

```bash
bdfetch room --school 83 --building <楼栋> --floor <楼层> --room <房间>
bdfetch room --school 83 --building <楼栋> --floor <楼层> --room <房间> --with-balance
bdfetch room --school 83 --building <楼栋> --floor <楼层> --scan-floor --out room_meters.json
bdfetch room --school 83 --building <楼栋> --floor <楼层> --scan-floor --resume --out room_meters.json
```

### `monitor`

```bash
bdfetch monitor --school 83 --meter <表号> --minutes 15 --interval 30
```

### `info`

```bash
bdfetch info --school 83
bdfetch info --school-name 中国科学技术大学
```

---

## 支持学校/校区

探测时间：`2026-07-28T15:25:10` · 站点学校列表共约 140 条，按免 OAuth 能力分层如下。

| 分层 | 数量 | 含义 | 本 CLI |
|------|-----:|------|--------|
| **full** | 55 | 表号 + 余额页可用；账单/明细多数可用 | **默认支持**（`bdfetch schools`） |
| **meter_bill** | 9 | 能拿表号；账单和/或日明细可用，**余额页当时未出数** | **有限支持**：可试 `--force` 查账单/明细，余额不保证 |
| **cascade_ok** | 7 | 房间级联通，但绑房后**未解析到表号** | **有限支持**：可试 `buildings` 级联，表号/余额不保证 |
| selectarea_only | 26 | 仅能选校，无楼栋级联 | 基本不可用 |
| fail | 43 | 超时等（多为独立部署/入口不可达） | 不可用 |

查询：`bdfetch meter --school <id> --meter <表号>`；完整 full 清单也可用 `bdfetch schools` 或包内 `src/electricity/data/supported_schools.json`。

> 下表**不含**真实表号与宿舍楼栋。能力以探测当时为准，站点可能变更。`full` 中「账单 N」表示月账单页当时失败，余额/明细通常仍可用。

### 完整支持（full，55）

| id | 学校/校区 | 余额 | 账单 | 明细 |
|----|-----------|:----:|:----:|:----:|
| 5 | 爱久公寓 | Y | Y | Y |
| 54 | 广东工业大学(大学城东西区/东风路/龙洞校区) | Y | Y | Y |
| 55 | 四川音乐学院 | Y | Y | Y |
| 57 | 临沂大学 | Y | Y | Y |
| 59 | 陕西师范大学雁塔校区 | Y | N | Y |
| 61 | 广州新华学院 | Y | N | Y |
| 64 | 北部湾职业技术学校 | Y | N | Y |
| 67 | 广西水产畜牧学校 | Y | Y | Y |
| 71 | 广西现代职业技术学院 | Y | N | Y |
| 72 | 四川农业大学都江堰校区 | Y | N | Y |
| 73 | 浙江大学海宁校区 | Y | Y | Y |
| 74 | 浙江工商大学 | Y | Y | Y |
| 75 | 花果园购物中心 | Y | Y | Y |
| 78 | 西安建筑科技大学 | Y | Y | Y |
| 80 | 中国科学技术大学 | Y | Y | Y |
| 81 | 江西生物科技职业学院 | Y | Y | Y |
| 82 | 江西应用技术职业学院 | Y | Y | Y |
| 83 | 江西师范大学 | Y | Y | Y |
| 86 | 西安美术学院 | Y | Y | Y |
| 87 | 桂林电子科技大学 | Y | Y | Y |
| 92 | 广西农业职业技术大学 | Y | Y | Y |
| 94 | 四川农业大学家属区 | Y | Y | Y |
| 96 | 云南农业大学热带作物学院 | Y | Y | Y |
| 97 | 浙江工商大学杭州商学院 | Y | N | Y |
| 99 | 深圳市福田区电通管理服务部 | Y | Y | Y |
| 101 | 华东石油技师学院 | Y | Y | Y |
| 102 | 赣南师范大学 | Y | Y | Y |
| 103 | 浙江农林大学暨阳学院 | Y | N | Y |
| 104 | 广西华侨学校 | Y | Y | Y |
| 105 | 中北大学 | Y | N | Y |
| 106 | 广东南华工商职业学院广州校区 | Y | N | Y |
| 107 | 广东南华工商职业学院清远校区 | Y | Y | Y |
| 109 | 新疆师范大学 | Y | Y | Y |
| 110 | 四川希望城 德禧物业 | Y | Y | Y |
| 114 | 东乡高级技工学校 | Y | Y | Y |
| 119 | 广东南华工商职业学院清远校区教1/学3/5号楼 | Y | N | Y |
| 122 | 内江师范学院 | Y | Y | Y |
| 125 | 广州工程技术职业学院 | Y | Y | Y |
| 127 | 湖南高速铁路职业技术学院(衡阳) | Y | Y | Y |
| 128 | 广东工业大学(揭阳校区) | Y | Y | Y |
| 129 | 广西质量工程职业技术学院电控缴费 | Y | Y | Y |
| 130 | 淮阴师范学院 | Y | Y | Y |
| 132 | 遂宁工程职业学院 | Y | Y | Y |
| 135 | 成都纺织高等专科学校(邛崃校区) | Y | N | Y |
| 136 | 广东工业大学(番禺校区) | Y | Y | Y |
| 137 | 南昌大学慧苑学生公寓 | Y | Y | Y |
| 138 | 贵州工商职业学院 | Y | N | Y |
| 139 | 广东轻工职业技术大学 | Y | Y | Y |
| 142 | 遵义医科大学 | Y | Y | Y |
| 144 | 衡阳中亿汽贸城 | Y | N | Y |
| 147 | 中国地质大学（北京） | Y | Y | Y |
| 148 | 云南农业大学(热院水电) | Y | Y | Y |
| 149 | 赣南医科大学第一临床医学院 | Y | Y | Y |
| 153 | 铜仁幼儿师范高等学校 | Y | Y | Y |
| 154 | 赣州南康远洋未来广场 | Y | N | Y |

### 有限支持 · 表号 + 账单/明细（meter_bill，9）

这些学校探测时能通过房间链路拿到表号，且账单和/或日明细可用，但 **`meter_main` 余额字段未读到**（部分走 `/room_main` 等路径，或余额页依赖更强会话）。  
可用尝试：

```bash
bdfetch meter --school <id> --meter <表号> --force --detail
# 可能只有 bill / detail 有数据，balance 为空
bdfetch buildings --school <id>   # 级联往往可用
```

| id | 学校/校区 | 表号 | 余额 | 账单 | 明细 | 说明 |
|----|-----------|:----:|:----:|:----:|:----:|------|
| 49 | 深职大官龙山园区 | Y | N | Y | Y | 余额页受限（曾探测 path=`/room_main`） |
| 50 | 深职大留仙洞园区 | Y | N | Y | Y | 余额页受限（曾探测 path=`/room_main`） |
| 79 | 深职大西丽湖园区 | Y | N | N | Y | 余额页受限（曾探测 path=`/room_main`） |
| 115 | 青岛大学 | Y | N | N | Y | 余额页受限（曾探测 path=`/room_main`） |
| 117 | 湖南铁道职业技术学院 | Y | N | Y | Y | 表号可用，余额页未出数（可能需微信会话） |
| 120 | 广西大学 | Y | N | Y | Y | 余额页受限（曾探测 path=`/room_main`） |
| 124 | 成都纺织高等专科学校(犀浦校区) | Y | N | Y | Y | 余额页受限（曾探测 path=`/room_main`） |
| 145 | 广西英华国际职业学院 | Y | N | Y | Y | 余额页受限（曾探测 path=`/room_main`） |
| 150 | 赣南医科大学(商户) | Y | N | Y | Y | 余额页受限（曾探测 path=`/room_main`） |

### 有限支持 · 仅房间级联（cascade_ok，7）

楼栋/楼层/房间 `getB` 级联可用，但 POST `/login` 绑房后 HTML **未解析出 comAddress**（锁房、空置、页面结构差异等）。  
可用尝试：`bdfetch buildings / floors / rooms`；**不要期望**稳定的 `room`→表号或 `meter` 余额。

| id | 学校/校区 | 级联 | 表号 | 说明 |
|----|-----------|:----:|:----:|------|
| 63 | 赣南医科大学 | Y | N | 楼栋级联通，绑房未解析出表号 |
| 65 | 长安大学 | Y | N | 楼栋级联通，绑房未解析出表号 |
| 69 | 海口经济学院 | Y | N | 楼栋级联通，绑房未解析出表号 |
| 90 | 深圳职业技术大学旺棠公寓 | Y | N | 楼栋级联通，绑房未解析出表号 |
| 116 | 北京师范大学·珠海 | Y | N | 楼栋级联通，绑房未解析出表号 |
| 133 | 四川建筑职业技术学院德阳校区 | Y | N | 楼栋级联通，绑房未解析出表号 |
| 134 | 四川建筑职业技术学院成都校区 | Y | N | 楼栋级联通，绑房未解析出表号 |

### 暂不可用（摘要）

- **selectarea_only（26）**：能 `selectarea`，但无楼栋级联数据（如部分校区未开通树形结构）。不逐校列出。
- **fail（43）**：探测超时或入口不可达。常见于名单里有、但 H5 实际独立域名/未部署在 `bd.bdfairy.cn` 的「主校」条目（如部分综合大学 id 较小的项）。不逐校列出。

若你的学校在「有限 / 不可用」里，可再自行 `bdfetch meter --school <id> --meter <表号> --force` 试探；成功不代表已并入默认 full 列表。


---

## 作为库使用

```python
from electricity import query_meter, query_room, list_schools, get_school

for s in list_schools(query="师范"):
    print(s["id"], s["name"], s.get("ok_bill"))

r = query_meter(
    "<表号>",
    area_id="83",
    area_name="江西师范大学",
    include_detail=True,
)
print(r["balance"]["total_yuan"])

room = query_room(
    area_id="83",
    area_name="江西师范大学",
    building="<楼栋>",
    floor="<楼层>",
    room="<房间>",
    campus="<校区标签>",   # 可选；默认可与校名相同
    campus_id="001001",    # 见 schools 数据中的 campus_root
)
print(room["meter"])
```

### 包结构

```text
.
├── README.md
├── pyproject.toml
├── requirements.txt         # requests
├── LICENSE
├── .gitignore
└── src/electricity/
    ├── __init__.py          # 公开 API
    ├── __main__.py          # python -m electricity
    ├── cli.py               # bdfetch 入口
    ├── meter.py             # 表号直查
    ├── room.py              # 房间级联
    ├── schools.py           # 55 校注册表
    ├── session.py           # 匿名会话 / 选校
    ├── client.py            # UA 与站点常量
    ├── util.py
    └── data/supported_schools.json
```

---

## HTTP 链路

```text
GET  /?id={areaId}
POST /selectarea  {areaId, areaName}
POST /selectmeter {comAddress, hidType:电表, room:""}
GET  /meter_main
GET  /electricbill
POST /electricdetail   # 必须 POST（GET 会 302，勿用）

POST /getB  {bID|fID|rID1}
POST /login {buildingInfo, buildingID}
```

| 字段 | 含义 |
|------|------|
| `yffye` / `zye` / `bzdye` | 预付费 / 总余额 / 补助（元） |
| `zydl` | 累计电量（度） |
| `dbzt` / `cbsj` | 闸位 / 抄表时间 |
| `qcdl` `qmdl` `ydl` `ydje` | 期初、期末、用电量、金额 |
| `sj` | 日明细日期 |

---

## 开发

```bash
python -m venv .venv
# Windows: .\.venv\Scripts\activate
pip install -e .

bdfetch schools
bdfetch meter --school 83 --meter <表号> --no-dump
```

用 uv：

```bash
uv venv
uv pip install -e .
uv run bdfetch schools
```

构建分发：

```bash
pip install build
python -m build
# → dist/*.whl dist/*.tar.gz
```

---

## 注意事项

1. 扫层 / 批量请控制频率（默认房间扫描间隔约 1–2.5s）。
2. 无效表号可能 `status=empty`（超时或无读数）。
3. 已绑房间会话会尝试 `phonejcbd` 解绑再查。
4. 接口以站点为准，可能变更。
5. 请使用本人有权查询的数据，勿公开真实表号与房间信息。

---

## 许可证

MIT — 见 [LICENSE](./LICENSE)。

使用风险自负；请遵守学校与服务方相关规定。
