# KLineChart Pro + AKShare Gateway

面向第三方应用的行情网关组件：后端提供统一数据接口与 WS 推送，内置 AKShare Provider（可选依赖），前端提供 KLineChart Pro datafeed 适配器。你只需启动网关并引入 datafeed，即可在自己的应用里使用 KLineChart Pro。

## 你能得到什么
- **后端网关**：历史 K 线 + 实时 WS 推送
- **前端 datafeed**：直接喂给 KLineChart Pro
- **标准化接口**：后续可替换/扩展数据源

## 功能
- 历史 K 线：`1m/5m/15m/30m/60m/1d/1w/1M`
- 实时推送：WS 订阅，后端合成 bar
- 标的搜索：A 股代码/简称
- 交易日历：支持特殊交易时段/停市日期配置
- 缓存：内存默认，可选 Redis
- Demo：KLineChart Pro 前端接入示例

## 架构（简述）
```
Frontend (KLineChart Pro)
  └─ datafeed -> Gateway (FastAPI)
                     └─ AKShare
```

## 目录
- `packages/backend` 后端网关（FastAPI）
- `packages/datafeed` 前端 datafeed 适配器
- `examples/web-demo` 最小可运行 demo
- `docs` 设计文档

## 第三方应用接入步骤

### 1) 启动后端网关
方式 A：PyPI（发布后可用）
```bash
python -m pip install klinecharts-pro-akshare-gateway[akshare]
klinecharts-pro-akshare-gateway --host 0.0.0.0 --port 8000
```

方式 B：Clone 源码
```bash
git clone https://github.com/chenjiangbo/klinecharts-pro-akshare-gateway.git
cd klinecharts-pro-akshare-gateway
python -m pip install -e "packages/backend"
python -m pip install -e "packages/backend[akshare]"
python -m uvicorn klinecharts_pro_akshare_gateway.main:app --app-dir packages/backend --host 0.0.0.0 --port 8000
```

### 2) 构建并引入 datafeed（两种方式任选）
方式 A：在你的前端项目中直接引用本仓库构建产物  
```bash
cd packages/datafeed
npm install
npm run build
```
然后在你的前端项目中引用 `packages/datafeed/dist/index.js`。

方式 B：在你的前端项目中用本地路径安装  
```bash
# 在你的前端项目里
npm install ../packages/datafeed
```

### 3) 在前端使用 datafeed + KLineChart Pro
```ts
import { KLineChartPro } from "@klinecharts/pro";
import { createAkshareGatewayDatafeed } from "klinecharts-pro-akshare-datafeed";

const datafeed = createAkshareGatewayDatafeed({
  baseUrl: "http://your-gateway-host:8000",
});

const chart = new KLineChartPro({
  container: document.getElementById("chart"),
  symbol: { ticker: "600519.SH", name: "贵州茅台" },
  period: { multiplier: 1, timespan: "minute", text: "1m" },
  datafeed,
});
```

## 接口一览
- `GET /api/v1/symbols/search`
- `GET /api/v1/bars/history`
- `GET /api/v1/ws`
- `GET /api/v1/health`

## WebSocket 协议
订阅：
```json
{ "op": "subscribe", "symbol": "600519.SH", "period": "1m" }
```
推送：
```json
{ "op": "bar", "symbol": "...", "period": "...", "bar": { "ts": 0, "open": 0, "high": 0, "low": 0, "close": 0, "volume": 0, "amount": 0, "is_closed": false } }
```
取消订阅：
```json
{ "op": "unsubscribe", "symbol": "600519.SH", "period": "1m" }
```
状态事件（可选）：
```json
{ "op": "status", "message": "snapshot failed", "level": "warning", "code": "snapshot_failed" }
```

## 数据规范
- `ts` 为 **UTC 毫秒时间戳**，分桶以 `Asia/Shanghai` 计算
- 标的格式：`600519.SH` / `000001.SZ`
- period 映射：
  - `1m/5m/15m/30m/60m` -> 分钟
  - `1d/1w/1M` -> 日/周/月

## 配置（常用）
| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `TIMEZONE` | `Asia/Shanghai` | 时区 |
| `TRADING_SESSIONS` | `09:30-11:30,13:00-15:00` | 常规交易时段 |
| `SPECIAL_TRADING_SESSIONS` | `{}` | 特殊交易日时段（JSON） |
| `CLOSED_DATES` | 空 | 停市日期（逗号分隔） |
| `SNAPSHOT_POLL_INTERVAL_SECONDS` | `3` | 实时轮询间隔 |
| `IDLE_BACKOFF_SECONDS` | `30` | 非交易时段退避 |
| `MAX_ACTIVE_SYMBOLS` | `200` | 最大订阅标的 |
| `HISTORY_MAX_LIMIT` | `2000` | 历史最大返回条数 |
| `MINUTE_HISTORY_MAX_DAYS` | `7` | 分钟历史最大跨度 |
| `CACHE_BACKEND` | `memory` | 缓存后端 |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis 地址 |
| `CORS_ALLOW_ORIGINS` | `http://127.0.0.1:5173` | CORS 白名单 |
| `AKSHARE_SILENT_PROGRESS` | `false` | 是否静默进度条 |

## 常见问题
- **重启后会重新拉取数据**：默认使用内存缓存；可开启 Redis 或在应用侧做持久化。
- **分钟历史返回空**：AKShare 数据可用性受限，会自动回退到最近交易日重试。

## Demo（可选）
```bash
cd examples/web-demo
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

## 文档
详见 `docs/KLineChart Pro + AKShare 对接方案详细设计文档.md`。
