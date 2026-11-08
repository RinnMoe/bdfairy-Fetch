# 本地环境与长安大学验证记录

日期：`2026-11-08`（Asia/Shanghai）
工作区：`E:\Sync\Github\bdfairy-Fetch`
定位：**长安大学专用 fork**。上游的 55 校通用清单、多校能力分层和旧结论已移除/更新。

- 上游原仓库：[guiguisocute/bdfairy-Fetch](https://github.com/guiguisocute/bdfairy-Fetch)（多校通用版，MIT）
- 本仓库：[RinnMoe/bdfairy-Fetch](https://github.com/RinnMoe/bdfairy-Fetch)（fork）
- 同步策略：不自动跟随上游多校更新；本仓库只维护长安大学。

> 本文不记录真实表号、房间号与余额金额；命令中的 `<表号>` / `<房间>` 请替换为你本人有权查询的数据。

---

## 1. 环境

| 项 | 值 |
|----|----|
| OS | Windows（Git Bash / PowerShell） |
| Python | 3.13.9 |
| 包管理器 | uv 0.8.23 |
| 虚拟环境 | `.venv/` |
| 运行依赖 | `requests` 2.34.2 |
| 项目安装 | `uv pip install --python .venv/Scripts/python.exe -e .` |

```bash
uv venv .venv --python 3.13
uv pip install --python .venv/Scripts/python.exe -e .

./.venv/Scripts/bdfetch.exe --help
./.venv/Scripts/python.exe -m electricity --help
# 或
uv run bdfetch --help
```

---

## 2. 本次重构内容

### 移除

- `src/electricity/schools.py`：55 校注册表/多校解析逻辑。
- `src/electricity/data/supported_schools.json`：上游 55 所 full 清单。
- `src/electricity/data/known_schools.json`：上一版临时 known 校区。
- CLI 的 `schools` 子命令，以及 `--school` / `--school-id` / `--school-name` / `--area-id` / `--area-name` / `--force` / `--only-bill` / `--only-detail` 参数。

### 新增/调整

- `src/electricity/tree.py`：静态树快照加载/查询/显式刷新；默认命令不访问 `/getB`。
- `src/electricity/data/changan_tree.json`：楼栋/楼层/房间静态快照（本次 88 栋 / 502 层 / 18,089 间，0 抓取错误，约 2.5MB）。
- `src/electricity/changan.py`：长安大学常量（`65` / `长安大学` / `001000`）、能力档案、`split_id` / `describe_id` 代号拆分。
- `src/electricity/data/changan.json`：能力、计数、分组、代号规则、验证备注。
- `room.py`：房间路径解析改用静态树；只保留 `/login` + `/selectmeter` 动态绑房；`--scan-floor` 跳过占位房间「充值前请确认房间」。
- `meter.py` / `session.py` / `client.py`：默认学校改为长安大学。
- `cli.py`：`buildings` / `floors` / `rooms` 读静态快照；`buildings --refresh` 显式刷新；`room` 静态解析 + 动态取表号。
- `README.md`：删除 55 校表格、`meter_bill` / `cascade_ok` / `selectarea_only` / `fail` 分层、旧「长安大学绑房未解析出表号」结论；改为长安大学单校文档，并区分静态/动态数据。
- `tests/test_offline.py`：长安大学档案、代号规则、静态树快照、表号解析、CLI 参数、公开 API。

---

## 3. 离线自检（无需网络）

```bash
./.venv/Scripts/python.exe -m unittest discover -s tests -v
```

结果：`Ran 26 tests ... OK`。

覆盖：

- 长安大学档案：`id=65`、`name=长安大学`、`campus_root=001000`、`tier=full`。
- 能力布尔值：buildings/floors/rooms/room_to_meter/balance/bill/detail。
- 计数：根接口 116 条、唯一 88 栋、6 个分组。
- 分组：`003=北院`、`004=东院`、`005=西院`、`006/007=渭水校区`、`008=混合`。
- 代号拆分：`root(6)+group(3)+building(6)+floor(6)+room(3)`。
- 静态树快照：88 栋 / 502 层 / 18,089 间；`003/1号公寓` 4 层 144 间；`1楼` 36 间；首项为占位房间。
- `extract_meters` / `extract_meter_rows` 能解析 `/selectmeter` 的 `JSON.parse('[{"comAddress":...}]')`，并保留一房多表（空调/照明）记录。
- CLI 已无 `schools` 子命令；`info/floors/rooms/room/meter/buildings --refresh` 参数解析正常。
- `from electricity import ...` 与 `__version__`。

---

## 4. 长安大学实测（静态树 + 动态查询）

站点：`http://bd.bdfairy.cn`（HTTP；请求带 MicroMessenger UA）。

| 步骤 | 结果 |
|------|------|
| `bdfetch buildings`（默认） | 读静态快照：88 栋 / 502 层 / 18,089 间；不访问 `/getB` |
| `bdfetch buildings --refresh` | 抓取全树并写入 `changan_tree.json`：88 栋 / 502 层 / 18,089 间，0 errors |
| `bdfetch floors --building 1号公寓 --group 003` | 读静态快照：4 层（1–4 楼） |
| `bdfetch rooms --building 1号公寓 --group 003 --floor 1楼` | 读静态快照：36 间（首项为占位「充值前请确认房间」） |
| `bdfetch room --building 1号公寓 --group 003 --floor 1楼 --room <房间>` | 静态树解析 + 动态 `/login` + `/selectmeter`；`ok=true`，表号已脱敏 |
| `bdfetch meter --meter <表号> --no-bill --json` | `status=valid`；余额、补助、总余额、累计电量、闸位、抄表时间、计费类型可读 |
| `bdfetch meter --meter <表号> --detail --json` | 月账单 `2026-10`：`qcdl/qmdl/ydl/ydje` 均可读；日明细 `2026-11`：每日 `sj/ydl/ydje` 可读 |
| `balance.room` | `null`（站点 `roomaddr=undefined`） |

默认 `buildings` / `floors` / `rooms` 不访问 `/getB`：用 `--base http://127.0.0.1:9` 仍能返回快照，已验证。

### 多表房间

实测某渭水房间返回 **2 个表**，`PipLineName` 分别带 `(空调)` / `(照明)`：

- 两个表都有效，可独立查询余额 / 月账单 / 日明细；一个表合闸有余额，另一个表跳闸且余额为 0（具体数值不记录）。
- `room` 返回 `meters[]`（全部表号）与 `meter_rows[]`（设备明细，含 `PipLineName`、`EqptTypeName` 等）；`meter` 只是第一个。
- `--with-balance` 会逐个查询所有表；`--scan-floor` 导出记录在多表时带 `meters[]`，不会丢表。

复现命令：

```bash
./.venv/Scripts/bdfetch.exe info
./.venv/Scripts/bdfetch.exe buildings
./.venv/Scripts/bdfetch.exe buildings --refresh     # 仅结构变更时
./.venv/Scripts/bdfetch.exe floors --building 1号公寓 --group 003
./.venv/Scripts/bdfetch.exe rooms  --building 1号公寓 --group 003 --floor 1楼
./.venv/Scripts/bdfetch.exe room   --building 1号公寓 --group 003 --floor 1楼 --room <房间> --json
./.venv/Scripts/bdfetch.exe meter  --meter <表号> --detail --no-dump --json
```

---

## 5. 代号规则证据

采样：`003–008` 六个分组、每组第一栋、前 4–5 层、前 5 个房间。

- **楼层校验**：22 次，`floor` 段全部等于楼名数字（1楼=`000001`，2楼=`000002`…）。
- **房间校验**：30 次，`room` 段全部符合“楼层内顺序号”规则。
  - `003` 组 1号公寓：101→`001`、102→`002`、103→`003`、104→`004`、**106→`005`**（105 缺失不影响序号）。
  - 最后 `公寓门卫=035`、占位房间 `充值前请确认房间=036`。
- **楼栋序号**：组内顺序，不是楼号。
  - `004` 组：3号公寓=`000001`、4号=`000002`、5号=`000003`、8号=`000004`、9号=`000005`。
  - `003` 组：西门科技服务1号公寓=`000012`、12号公寓=`000013`。
- **分组节点**：`POST /getB {"bID":"001000003"}` 返回 13 栋；`bID` 可直接查 root(6)/group(9)/building(15)。

完整规则已写入 [README.md](./README.md#长安大学代号规则) 和 `data/changan.json`。

---

## 6. 站点行为与注意事项

1. **绑房状态 `band=1`**：绑定过房间后 `selectarea` 返回 `band=1`，此时 `/getB` 返回 500；刷新静态树或动态查询时程序会自动 `POST /phonejcbd` 解绑后重试。页面提示换房次数上限 4 次，批量扫描请控制频率。
2. **占位房间**：部分楼栋 `1楼` 首个房间是「充值前请确认房间」，`JSON.parse('[]')` 无表号；`--scan-floor` 已跳过。
3. **OAuth 跳转**：非微信 UA 访问 `GET /?id=65` 会 302 到 `open.weixin.qq.com`；API 链路使用 MicroMessenger UA，不受影响。
4. **根接口重复**：刷新时 `bID=001000` 返回 116 条，其中 88 个唯一 `BuildingID`；快照按 `BuildingID` 去重。
5. **楼名重复**：`1号公寓` 同时出现在 `003/005/006/007` 组；必须用 `--group` 或 15 位楼栋 ID。
6. **房间序号不是房号**：`room` 段是楼层内顺序号，106 可能对应 `005`。
7. **房间地址缺失**：`roomaddr=undefined`，`balance.room` 为 `null`。
8. **静态快照会过期**：站点新增/调整楼栋房间后，默认查询可能找不到；运行 `bdfetch buildings --refresh` 更新 `changan_tree.json`。

---

## 7. 限制

- 静态树快照可能过期：站点新增/调整楼栋房间后需运行 `bdfetch buildings --refresh`；全树刷新会访问数百次 `/getB`，耗时数分钟。
- 本次只抽样了 `003` 组 `1号公寓` `1楼` 的 1 个真实房间及其表号；其他楼栋/楼层/房间需自行用 `buildings/floors/rooms/room` 验证。
- 自定义月份 `--month`、整层扫描 `--scan-floor`、`monitor` 轮询未完整跑完（绑房/换房次数限制）。
- 充值流水 / 微信 OAuth 不在本项目覆盖范围。
- 接口以站点为准，可能变更；本项目只覆盖长安大学，不保证其他学校可用。
- 静态快照包含站点公开的楼栋/楼层/房间名称与 ID；不含表号、余额金额、个人绑定信息。`output/` 与探针文件已被 `.gitignore` 忽略。

---

## 8. 结论

- 依赖补齐完成：`.venv` + editable install，`bdfetch`、`python -m electricity`、`from electricity import ...` 均可运行。
- 项目已从“55 校通用工具”收敛为“长安大学单校研究/适配工具”；上游过时/错误的 55 校分层与 `cascade_ok` 结论已清除。
- 楼栋/楼层/房间改为本地静态快照（88 栋 / 502 层 / 18,089 间），默认查询不访问 `/getB`；仅 `buildings --refresh` 显式刷新。
- 长安大学已验证：静态树 → 房间 → 动态表号 → 余额 → 月账单 → 日明细；一房多表（空调/照明）也会全部保留。
