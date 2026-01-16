# 1. 背景与目标
## 1.1 背景
我们选择 **KLineChart Pro** 作为前端图表（含指标与画线 UI），选择 **AKShare** 作为第一阶段数据源（A 股）。由于 AKShare 是 Python 采集库而非云服务，我们需要在后端搭建一个 **行情网关服务（Market Data Gateway）**，为前端提供统一的历史 K 线与实时更新流。

## 1.2 目标（Goals）
1. 前端 KLineChart Pro 可展示 A 股 K 线（至少日线 + 分钟线之一）。
2. 支持指标（如 MA/EMA）正常计算显示（只要提供 OHLCV）。
3. 支持用户画线（趋势线/斐波那契等）——这由 KLineChart Pro UI 自己完成，后端只需保证数据时间轴稳定。
4. **刷新策略不落到前端**：实时更新由后端统一调度并通过 WS/SSE 推送，前端只订阅。
5. 支持标的搜索/选择（Symbol Search）。
6. 可扩展：后续新增 TuShare 作为第二数据源时，前端不改；只新增 Provider。

## 1.3 非目标（Non-goals）
+ 不在第一阶段实现“缠论笔”的自动识别算法（可作为后续扩展：由后端算转折点，再用 overlay 绘制）。
+ 不做交易、下单、风控等。
+ 不承诺全市场同时订阅（先聚焦 1~200 标的级别）。

---

# 2. 总体架构
## 2.1 架构概览
```plain
+--------------------+        HTTP/WS        +---------------------------+
|  Frontend          |  <---------------->   |  Market Data Gateway      |
|  KLineChart Pro    |                       |  (FastAPI)                |
|  CustomDatafeed    |                       |                           |
+--------------------+                       |  - Provider(AKShare)      |
                                            |  - BarBuilder/Aggregator  |
                                            |  - Cache (in-mem/Redis)   |
                                            |  - WS Hub (pub-sub)       |
                                            +---------------------------+
                                                        |
                                                        | Python calls
                                                        v
                                                +----------------+
                                                | AKShare Library |
                                                +----------------+
```

## 2.2 关键设计点
+ 前端只实现 **CustomDatafeed**（search/history/subscribe/unsubscribe），不做择时逻辑。
+ 后端做两类能力：
    1. **历史数据**：按 symbol+period 拉取并缓存；
    2. **实时更新**：统一轮询快照（尽量批量），用 BarBuilder 合成当前 bar，推送给订阅者。

---

# 3. 技术选型
## 3.1 后端
+ Python 3.12+
+ FastAPI 0.111+ + Uvicorn 0.30+
+ Pydantic v2
+ 可选：Redis（默认关闭；本地/单实例用 in-memory；多实例/共享缓存时启用）

## 3.2 前端
+ KLineChart Pro（你项目既定）
+ 自定义 Datafeed（TypeScript）

## 3.3 配置项建议（最小集合）
+ `TIMEZONE=Asia/Shanghai`
+ `TRADING_SESSIONS=09:30-11:30,13:00-15:00`
+ `SPECIAL_TRADING_SESSIONS={}`（JSON，指定特殊交易日时段，如 `{"2025-01-15":"09:30-11:30"}`）
+ `CLOSED_DATES=`（逗号分隔停市日期，如 `2025-01-01,2025-10-01`）
+ `SNAPSHOT_POLL_INTERVAL_SECONDS=3`
+ `IDLE_BACKOFF_SECONDS=30`
+ `MAX_ACTIVE_SYMBOLS=200`
+ `CACHE_BACKEND=memory|redis`（默认 `memory`）
+ `REDIS_URL=redis://localhost:6379/0`（仅当启用 Redis）
+ `HISTORY_MAX_LIMIT=2000`
+ `MINUTE_HISTORY_MAX_DAYS=7`
+ `WS_PING_INTERVAL_SECONDS=25`
+ `CORS_ALLOW_ORIGINS=http://127.0.0.1:5173`
+ `AKSHARE_SILENT_PROGRESS=false`（是否静默 AKShare 进度条）

---

# 4. 数据模型与命名规范
## 4.1 Symbol 规范（统一表示）
统一内部 symbol 格式为：

+ `600519.SH`（上交所）
+ `000001.SZ`（深交所）
+ `430047.BJ`（北交所，后续可选）

**原因**：前端/后端一致；同时易映射到 AKShare 各种函数所需的编码格式（如 `sh600519` 等）。

### 映射规则
+ `600519.SH` -> `sh600519`
+ `000001.SZ` -> `sz000001`
+ `430047.BJ` -> `bj430047`（如 AKShare 支持）

写一个工具函数 `to_akshare_symbol(symbol: str) -> str` 统一映射。

## 4.2 Period 规范
对齐 KLineChart Pro 的 period 概念（multiplier + timespan），并提供**默认支持集合**，使用方可裁剪。

内部约定 `period_id`（默认）：

+ 分钟：`1m`, `5m`, `15m`, `30m`, `60m`
+ 日/周/月：`1d`, `1w`, `1M`

映射示例：

+ `timespan='minute' & multiplier=30 => 30m`
+ `timespan='day' & multiplier=1 => 1d`

---

# 5. API 契约（后端网关）
这些接口是前端 CustomDatafeed 唯一依赖点。后续接 TuShare 也不变。

## 5.1 标的搜索
### `GET /api/v1/symbols/search?q=茅台&limit=20`
Response:

```json
{
  "items": [
    {
      "symbol": "600519.SH",
      "name": "贵州茅台",
      "exchange": "SSE",
      "type": "stock",
      "currency": "CNY",
      "timezone": "Asia/Shanghai"
    }
  ]
}
```

实现建议：

+ AKShare：加载 A 股代码表（代码-简称），做代码/中文简称 contains 匹配（第一阶段不做拼音/模糊）
+ 参数约定：
    - `q` 为空时返回空列表
    - `limit` 做上限截断（例如最大 50）

缓存：

+ 股票列表每天更新一次（或启动时加载 + 24h 刷新）

## 5.2 历史 K 线
### `GET /api/v1/bars/history?symbol=600519.SH&period=1d&from=2025-01-01&to=2026-01-15&limit=2000`
Response:

```json
{
  "symbol": "600519.SH",
  "period": "1d",
  "items": [
    {
      "ts": 1736899200000,
      "open": 1700.1,
      "high": 1712.0,
      "low": 1690.0,
      "close": 1708.0,
      "volume": 1234567,
      "amount": 987654321.12
    }
  ],
  "next_from": null
}
```

字段约定：

+ `ts`：毫秒时间戳（KLineChart 通常用 ms，统一 ms）
+ `volume`：成交量（手/股按源数据原样；只要一致即可）
+ `amount`：成交额（可选，没有就返回 null 或省略）

参数语义（建议）：

+ `period` 为 `1d/1w/1M`：`from/to` 使用 `YYYY-MM-DD`（按交易日）
+ `period` 为分钟级：`from/to` 使用 ISO datetime（或 ms），按 `Asia/Shanghai` 解析
+ `from/to` 均为**闭区间**，历史返回按 `ts` **升序**
+ 无数据时返回 `items: []`，`next_from: null`
+ `1w/1M` 的历史由日线聚合得到（无需源侧提供周/月）

分页：

+ 暂不强制分页，但提供 `limit` 与 `next_from` 以便未来支持长历史。
    - `next_from` 为下一次请求的起点（等于最后一根 bar 的 `ts` + 1ms）

## 5.3 实时订阅（WebSocket）
### `GET /api/v1/ws`
客户端连接后发送：

```json
{ "op": "subscribe", "symbol": "600519.SH", "period": "1m" }
```

服务端推送：

```json
{
  "op": "bar",
  "symbol": "600519.SH",
  "period": "1m",
  "bar": {
    "ts": 1736971860000,
    "open": 1708.0,
    "high": 1710.0,
    "low": 1707.5,
    "close": 1709.5,
    "volume": 12000,
    "amount": 20400000.0,
    "is_closed": false
  }
}
```

取消订阅：

```json
{ "op": "unsubscribe", "symbol": "600519.SH", "period": "1m" }
```

心跳：

+ 服务器每 20~30s 发 ping，客户端 pong；或用 WS 原生 ping/pong。
+ 建议增加订阅确认与错误回包：
    - 成功：`{ "op": "subscribed", "symbol": "...", "period": "..." }`
    - 失败：`{ "op": "error", "reason": "invalid symbol/period" }`
+ 状态推送（可选增强）：
    - `{ "op":"status", "message":"...", "level":"warning|error", "code":"snapshot_failed" }`

---

# 6. AKShare 数据接入设计（Provider）
## 6.1 Provider 抽象
定义统一接口，后续接 TuShare 只新增一个 Provider。

```python
class MarketDataProvider(Protocol):
    def search_symbols(self, q: str, limit: int) -> list[SymbolInfo]: ...
    def get_daily_history(self, symbol: str, start: date, end: date) -> list[Bar]: ...
    def get_minute_history(self, symbol: str, period: str, start: datetime, end: datetime) -> list[Bar]: ...
    def get_realtime_snapshot_batch(self, symbols: list[str]) -> dict[str, Snapshot]: ...
    def get_trading_calendar(self) -> set[str]: ...
```

### Snapshot 结构（用于合成 bar）
```python
@dataclass
class Snapshot:
    ts: datetime          # 数据获取时间/或源时间
    last: float           # 最新价
    open: float|None
    high: float|None
    low: float|None
    prev_close: float|None
    volume_total: float|None   # 当日累计成交量（关键：用于 volume delta）
    amount_total: float|None   # 当日累计成交额
```

## 6.2 AKShare 具体用法（建议路线）
+ **symbols**：用 AKShare 的 A 股代码表接口构建 symbol 字典（启动加载，定时刷新）
+ **daily history**：用 AKShare 日线历史接口
+ **realtime snapshot**：用 AKShare 的沪深京 A 股实时行情（尽量批量）
+ **minute history（可选）**：AKShare 分钟数据通常有时间/范围限制（先满足“近期分钟线”即可）
+ 若分钟历史返回空，可回退至最近交易日的 09:30–15:00 区间重试

第一阶段建议：`1d` 必做；`1m` 可做（近期分钟历史 + 实时合成）。

---

# 7. 实时刷新策略：BarBuilder（核心，前端不需要再管）
## 7.1 为什么必须有 BarBuilder
AKShare 不会替你提供“订阅流”；它是拉取接口。你要 “实时更新 K”，就必须由后端：

1. 定时拉快照；
2. 把快照合成 period bar；
3. 推送给订阅者。

## 7.2 交易时段（A 股）
默认交易时段（北京时间 Asia/Shanghai）：

+ 上午：09:30–11:30
+ 下午：13:00–15:00

设计上做成可配置（避免特殊情况/未来市场规则变化）。
+ 需要交易日历（节假日/临时停市）支持：
    - 启动时加载交易日列表并缓存（AKShare）
    - 非交易日不合成 bar，轮询退避

## 7.3 刷新频率
建议配置（可热更新）：

+ `snapshot_poll_interval_seconds`: 3（默认 3s，生产可 3~5s）
+ `idle_backoff`: 非交易时段自动退避到 30~60s（只用于维持连接/心跳，不推 bars）

## 7.4 合成规则（分钟线）
以 `1m` 为例，其他周期用分桶聚合（见 7.6）：

+ `bar_start = floor(ts to minute)`
+ `open`：该 bar 的第一笔 `last`
+ `high/low`：该 bar 内 max/min(last)
+ `close`：最新 last
+ `volume`：使用快照 `volume_total` 做差分：
    - `delta_vol = max(0, snap.volume_total - prev_snap.volume_total)`
    - 将 `delta_vol` 累加到当前 bar
+ `amount`：同理 `amount_total` 做差分

### 边界处理
+ 快照缺字段：volume_total/amount_total 为空时，volume/amount 只能置 0 或跳过（记录告警）。
+ 停牌/无成交：last 不变且 volume_total 不变，bar 仍会推送 close（可降低推送频率）。
+ 交易日切换：检测 `volume_total` 重置或日期变化时，重置日内累计并新开 bar。

## 7.5 合成规则（日线）
日线必须“盘中可变”，避免你之前担心的“下午跌停日线不变”。

+ `bar_start = 当天 00:00:00`（或交易日标识）
+ `open`：取当天首次快照 last（或快照 open）
+ `high/low`：用累计 max/min(last)，或用快照 high/low（若可靠）
+ `close`：快照 last
+ `volume/amount`：用累计 volume_total/amount_total（或差分累加）

收盘后（>=15:00）：

+ 将 `is_closed = true`
+ 可触发一次“用 AKShare 日线接口校准当日 OHLCV”（可选增强）

## 7.6 多周期聚合（可配置）
周期集合由使用方配置。推荐做法：统一从**较小粒度**作为基础 bar 聚合：

+ 分钟级：例如使用方只需要 `30m`，可从 `1m` 或 `5m` 聚合（更省轮询可用 `5m`，更精细可用 `1m`）
+ 周/月：从 `1d` 聚合得到 `1w/1M`
+ 桶的 `open` = 第一根基础 bar open
+ `high` = max
+ `low` = min
+ `close` = 最后一根基础 bar close
+ `volume/amount` = sum

这样避免你为每个周期重复写逻辑，并允许不同场景选择不同基础粒度。
+ 约束：历史与实时使用**同一基础粒度**，避免时间轴与数值不一致。

## 7.7 推送策略（减少无意义推送）
+ 若当前 bar 的 close/volume/amount 均无变化：可跳过推送（可配）
+ 但至少每 30s 推送一次心跳 bar（保持 UI 更新）

---

# 8. WebSocket Hub 设计
## 8.1 订阅模型
+ 一个 WS 连接可订阅多个 `(symbol, period)`
+ 服务器维护：
    - `subs[(symbol, period)] -> set(connection_id)`
    - `active_symbols -> set(symbol)`（去重后用于批量拉快照）
+ 当某 symbol 没有任何订阅时，从 active_symbols 移除，减少轮询量。

## 8.2 并发与线程模型
+ FastAPI asyncio
+ 轮询任务：后台 `asyncio.create_task(poll_loop())`
+ poll_loop 每次：
    1. 取 active_symbols（快照批量拉）
    2. 更新 BarBuilder 状态
    3. 生成 bar events
    4. 广播到 hub
*AKShare 为同步调用，建议在 threadpool 中执行快照/历史查询，避免阻塞 event loop。*

---

# 9. 缓存、限流与可靠性
## 9.1 缓存
+ `symbols_cache`: 股票列表（内存 + 文件落盘可选）
+ `history_cache`（默认 in-memory，可切换 Redis）：
    - Key: `history:{symbol}:{period}:{from}:{to}`
    - TTL: 日线 6h，分钟线 5~15min
+ Redis 启用方式（配置即可，无需改代码）：
    - `CACHE_BACKEND=redis`
    - `REDIS_URL=redis://localhost:6379/0`

## 9.2 限流
AKShare 数据源可能对频繁请求敏感，因此必须：

+ 快照轮询 **批量** 优先
+ 限制最大 active_symbols（例如 200），超过则拒绝订阅或降级频率
+ 非交易时段停止轮询或极低频

## 9.3 错误与重试
+ 拉快照失败：指数退避（3s -> 5s -> 10s），并通过 WS 发 `"op":"status"` 告知前端“数据暂不可用”
+ 单个 symbol 数据缺失：不影响其他 symbol 推送

---

# 10. 前端 CustomDatafeed 设计（KLineChart Pro）
前端的职责：把 KLineChart Pro 的 datafeed 调用映射到后端 API，并把 WS 推送转换成图表更新回调。

## 10.1 需要实现的方法
+ `searchSymbols(searchText, ...)` -> 调 `/symbols/search`
+ `getHistoryKLineData(symbol, period, from, to)` -> 调 `/bars/history`
+ `subscribe(symbol, period, callback)` -> WS subscribe，收到 `"op":"bar"` 调 callback
+ `unsubscribe(symbol, period)` -> WS unsubscribe

## 10.2 Period 映射
+ period `{ multiplier: 1, timespan: 'minute' }` -> `"1m"`
+ `{1,'day'}` -> `"1d"`

## 10.3 重连策略
+ WS 断线：1s/2s/5s/10s 退避重连
+ 重连后自动重放订阅列表（客户端保存当前订阅集合）

---

# 11. 数据一致性与时间处理
+ 统一使用 `Asia/Shanghai` 进行交易日与分桶计算
+ `ts` 统一输出**UTC 毫秒时间戳**，但以 `Asia/Shanghai` 计算 bar 边界后再转换为 UTC ms
+ 对齐 bar start：分钟取整、日线以交易日为准

---

# 12. 安全与部署
## 12.1 安全
+ 第一阶段可不做鉴权（内网/测试）
+ 生产建议：
    - JWT 或 API Key
    - CORS 白名单
    - WS 同样校验 token

## 12.2 部署
+ 单实例：`uvicorn app:app --host 0.0.0.0 --port 8000`
+ 生产建议：Docker + Gunicorn(UvicornWorker)；Redis 可选（用于多实例共享订阅/缓存）
+ Redis 启用示例（可选）：
    - 配置：`CACHE_BACKEND=redis`，`REDIS_URL=redis://localhost:6379/0`
+ 若多实例 WS：
    - 建议使用 sticky session（本项目不规划 Redis pubsub）

---

# 13. 代码库结构（建议稿）
klinecharts-pro-akshare-gateway/

  packages/

    backend/                 # FastAPI 网关（核心）

      app/

        api/                 # REST 路由

        ws/                  # WS hub

        provider/            # AKShare provider

        barbuilder/          # 聚合/实时bar合成

        cache/               # 内存/Redis

      tests/

      pyproject.toml

      README.md



    datafeed/                # 前端 Datafeed 适配器（TS 包）

      src/

        index.ts             # createAkshareGatewayDatafeed()

        types.ts

      package.json

      README.md



  examples/

    web-demo/                # 最小可运行 demo（KLineChart Pro）

      src/

      vite.config.ts

      package.json



  docs/                      # 文档站（可用 VitePress/MkDocs）

  docker/                    # Dockerfile / docker-compose

  LICENSE

  NOTICE

  README.md





# 15. 实现参考：后端关键伪代码
## 15.1 轮询主循环
```python
async def poll_loop():
    while True:
        now = shanghai_now()
        if not is_trading_time(now):
            await asyncio.sleep(cfg.idle_sleep_seconds)
            continue

        symbols = hub.get_active_symbols()
        if not symbols:
            await asyncio.sleep(cfg.snapshot_poll_interval_seconds)
            continue

        try:
            snapshots = provider.get_realtime_snapshot_batch(symbols)
        except Exception as e:
            log.exception("snapshot failed")
            await asyncio.sleep(backoff.next())
            continue

        events = bar_builder.apply_snapshots(snapshots, now)
        for evt in events:  # evt: (symbol, period, bar)
            await hub.broadcast_bar(evt.symbol, evt.period, evt.bar)

        await asyncio.sleep(cfg.snapshot_poll_interval_seconds)
```

## 15.2 BarBuilder（分钟）
```python
def update_minute_bar(state, snap, now):
    bucket_ts = floor_to_minute(now)  # datetime
    cur = state.cur_bar_1m

    if cur is None or cur.bucket_ts != bucket_ts:
        # finalize previous
        if cur:
            cur.is_closed = True
            emit(cur)
        # start new
        cur = Bar(bucket_ts=bucket_ts, open=snap.last, high=snap.last, low=snap.last,
                  close=snap.last, volume=0, amount=0, is_closed=False)
        state.cur_bar_1m = cur

    cur.high = max(cur.high, snap.last)
    cur.low  = min(cur.low, snap.last)
    cur.close = snap.last

    if snap.volume_total is not None and state.prev_volume_total is not None:
        dv = max(0, snap.volume_total - state.prev_volume_total)
        cur.volume += dv
    state.prev_volume_total = snap.volume_total

    # amount similar
    emit(cur)  # 可做“变化检测”后再 emit
```

---

## 你接下来给 AI code 的“实现任务列表”
1. 建 FastAPI 项目骨架（models/routes/ws/hub/provider/bar_builder）
2. 实现 ProviderAkshare：symbols + daily_history + snapshot_batch（先做最小字段）
3. 实现 WS hub（subscribe/unsubscribe + active_symbols 管理）
4. 实现 BarBuilder：先 1m + 1d
5. 前端 CustomDatafeed：对接三类接口 + WS 重连
6. Demo：展示 600519.SH，日线盘中会变

---

如果你告诉我你后端项目目前的形态（**纯新建服务**还是要接到现有 Python 项目里；是否允许引入 Redis；预计同时订阅多少标的），我可以把这份设计文档进一步“收敛成具体目录结构 + 每个文件/类的职责 + 接口字段严格校验规则”，让 AI code 直接按模块生成代码而不是自己发挥。
