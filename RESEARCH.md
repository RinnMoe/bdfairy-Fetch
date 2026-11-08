# 长安大学研究结论与已知问题

日期：`2026-11-08`
范围：`bd.bdfairy.cn` `areaId=65`（长安大学）

本文记录实际踩过的坑与验证结论；命令中的 `<表号>` / `<房间>` 请替换为本人有权查询的数据。

---

## 1. 分组代码：`006` 有效，`007` 疑似重复/旧树

`006` 与 `007` 都显示“渭水校区”，楼栋名高度重叠，但不是简单别名：

| 代码 | 楼栋数 | 结构 | 实测 |
|-----:|-------:|------|------|
| `006` | 26 | 含 23A/23B | 1号公寓 101、1号公寓 406 均可绑房取表号 |
| `007` | 24 | 缺 23A/23B | 1号公寓 101、2号公寓 101、1号公寓 406 均无表号 |

结论：

- **渭水校区优先使用 `006`**。
- `007` 疑似重复/旧树，仅作 `006` 查不到时的兜底。
- `003/004/005` 是北院/东院/西院的独立区域树，同名楼栋不是重复。
- `008` 是跨区域混合组（渭水修建中心、北院花园、南院、东院青年公寓、西院平房等），不是渭水校区别名。

判断某个房间用哪个代码：

```bash
bdfetch room --building 1号公寓 --group 006 --floor 4楼 --room 渭水校区1号公寓4楼406 --json
bdfetch room --building 1号公寓 --group 007 --floor 4楼 --room 渭水校区1号公寓4楼406 --json
# ok=true 且 meters 非空 → 该代码有效
```

---

## 2. 网络/代理：TUN 模式导致瞬时无法访问

现象：`bdfetch room` / `meter` 报 `RemoteDisconnected`、`Empty reply from server`，甚至 HTTPS 握手失败；但过一会儿重试又正常。

实测对比：

| 时点 | 源地址 | DNS | 结果 |
|------|--------|-----|------|
| TUN 开启时 | `198.18.0.1`（TUN 典型网段） | `198.18.0.2`（fake-IP） | TCP 能连上，HTTP 空响应，约 5 秒后 `Empty reply`；HTTPS 握手失败 |
| TUN 关闭/直连时 | `10.81.167.127` | 真实 IP `119.29.80.149` | `HTTP/1.1 302` 正常 |

补充证据：同一 TUN 期间 `POST /selectarea` 曾返回 `200`，重试后 `room`/`meter` 也成功。说明不是“TUN 绝对访问不了”，而是**代理节点/出口 IP 瞬时不稳定，或站点对代理出口有限制/丢包**。

建议：

1. 给站点加直连规则，绕过 TUN：
   ```text
   DOMAIN-SUFFIX,bdfairy.cn,DIRECT
   ```
   也可把 `119.29.80.149` 加入直连。
2. 必须走代理时，换稳定节点，并尽量对该域名关闭 fake-IP / 使用真实 DNS。
3. 出现 `RemoteDisconnected` 先重试；静态树命令不依赖网络，动态命令才需要。

> 这是网络链路问题，不是项目逻辑 bug；同一命令在直连下正常。

---

## 3. 一房多表：空调 / 照明

长安大学部分房间有 **两个表**，例如渭水 1号公寓 406：

- `/selectmeter` 的 `data = ref(JSON.parse('[...]'))` 返回两条设备记录；
- `PipLineName` 分别带 `(空调)` / `(照明)`；
- 两个表都有效，可独立查询余额 / 月账单 / 日明细；
- 实测一个表合闸有余额，另一个表跳闸且余额为 0（具体数值不记录）。

项目已支持：

- `room` 返回 `meters[]`（全部表号）和 `meter_rows[]`（设备明细，含 `PipLineName` / `EqptTypeName`）；
- `meter` 只是第一个表（页面顺序）；
- `--with-balance` 逐个查询所有表；
- `--scan-floor` 导出多表房间时带 `meters[]`，不会丢表。

---

## 4. 静态树与动态数据

| 类型 | 数据 | 来源 | 更新方式 |
|------|------|------|----------|
| 静态 | 楼栋 / 楼层 / 房间树（88 栋 / 502 层 / 18,089 间） | `data/changan_tree.json` 本地快照 | 仅 `bdfetch buildings --refresh` |
| 动态 | 绑房、表号、余额、月账单、日明细 | `/login`、`/selectmeter`、`/meter_main`、`/electricbill`、`/electricdetail` | 每次查询实时请求 |

默认 `buildings` / `floors` / `rooms` / `room` 的路径解析不访问 `/getB`；只有 `buildings --refresh` 才重新抓取全树（约数分钟）。静态快照会过期，结构变更后需刷新。

---

## 5. 站点行为与坑

1. **绑房状态 `band=1`**：绑定过房间后 `selectarea` 返回 `band=1`，此时 `/getB` 返回 500；程序会自动 `POST /phonejcbd` 解绑后重试。
2. **占位房间**：部分楼栋 `1楼` 首个房间是「充值前请确认房间」，无表号；`--scan-floor` 会跳过。
3. **OAuth 跳转**：非微信 UA 访问 `GET /?id=65` 会 302 到 `open.weixin.qq.com`；API 链路使用 MicroMessenger UA，不受影响。
4. **根接口重复**：刷新时 `bID=001000` 返回 116 条，其中 88 个唯一 `BuildingID`；快照按 `BuildingID` 去重。
5. **楼名不唯一**：`1号公寓` 同时出现在 `003/005/006/007` 组；必须用 `--group` 或 15 位楼栋 ID。
6. **房间序号不是房号**：`room` 段是楼层内顺序号，106 可能对应 `005`。
7. **房间地址缺失**：`roomaddr=undefined`，`balance.room` 为 `null`。

---

## 6. 限制

- 静态树快照可能过期；全树刷新会访问数百次 `/getB`，耗时数分钟。
- 仅抽样了部分楼栋/房间；其他楼栋/房间需自行用 `buildings/floors/rooms/room` 验证。
- 自定义月份 `--month`、整层扫描 `--scan-floor`、`monitor` 轮询未完整跑完（绑房/换房次数限制）。
- 充值流水 / 微信 OAuth 不在本项目覆盖范围。
- 接口以站点为准，可能变更；本项目只覆盖长安大学。

---

## 7. 复现命令

```bash
bdfetch info
bdfetch buildings
bdfetch buildings --refresh
bdfetch floors --building 1号公寓 --group 006
bdfetch rooms  --building 1号公寓 --group 006 --floor 4楼
bdfetch room   --building 1号公寓 --group 006 --floor 4楼 --room 渭水校区1号公寓4楼406 --json
bdfetch meter  --meter <表号> --detail --no-dump --json
```
