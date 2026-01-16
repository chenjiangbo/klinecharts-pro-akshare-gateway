import { KLineChartPro } from "@klinecharts/pro";
import "@klinecharts/pro/dist/klinecharts-pro.css";
import type { Datafeed as ProDatafeed, Period as ProPeriod, SymbolInfo as ProSymbolInfo } from "@klinecharts/pro";

import { createAkshareGatewayDatafeed } from "@datafeed/index";
import type { Bar, Period } from "@datafeed/types";

const app = document.querySelector<HTMLDivElement>("#app");
if (!app) {
  throw new Error("missing app root");
}

const defaultSymbol = "600519.SH";
const defaultPeriod: Period = { multiplier: 1, timespan: "minute" };

app.innerHTML = `
  <div style="font-family: ui-sans-serif, system-ui; max-width: 900px; margin: 32px auto;">
    <h1>AKShare Gateway Demo</h1>
    <p>用于验证网关接口与 WS 推送，不依赖 KLineChart Pro。</p>
    <div style="display: grid; gap: 12px;">
      <div style="display: grid; gap: 6px; padding: 10px; border: 1px solid #ddd;">
        <div><strong>Status</strong></div>
        <div id="wsStatus">WS: idle</div>
        <div id="barStatus">Bars: 0</div>
        <div id="klineStatus">KLineChart Pro: not loaded</div>
      </div>
      <div id="chart" style="height: 520px; border: 1px solid #eee;"></div>
      <label>
        Backend URL
        <input id="baseUrl" value="http://127.0.0.1:8000" style="width: 100%; padding: 6px;" />
      </label>
      <label>
        Symbol
        <input id="symbol" value="${defaultSymbol}" style="width: 100%; padding: 6px;" />
      </label>
      <label>
        Period
        <select id="period" style="width: 100%; padding: 6px;">
          <option value="1m">1m</option>
          <option value="5m">5m</option>
          <option value="15m">15m</option>
          <option value="30m">30m</option>
          <option value="60m">60m</option>
          <option value="1d">1d</option>
        </select>
      </label>
      <div style="display: flex; gap: 12px;">
        <button id="search">Search</button>
        <button id="history">History</button>
        <button id="subscribe">Subscribe</button>
        <button id="unsubscribe">Unsubscribe</button>
      </div>
      <pre id="output" style="background: #f5f5f5; padding: 12px; min-height: 240px;"></pre>
    </div>
  </div>
`;

const output = document.querySelector<HTMLPreElement>("#output");
const wsStatus = document.querySelector<HTMLDivElement>("#wsStatus");
const barStatus = document.querySelector<HTMLDivElement>("#barStatus");
const klineStatus = document.querySelector<HTMLDivElement>("#klineStatus");
const searchBtn = document.querySelector<HTMLButtonElement>("#search");
const historyBtn = document.querySelector<HTMLButtonElement>("#history");
const subscribeBtn = document.querySelector<HTMLButtonElement>("#subscribe");
const unsubscribeBtn = document.querySelector<HTMLButtonElement>("#unsubscribe");

const baseUrlInput = document.querySelector<HTMLInputElement>("#baseUrl");
const symbolInput = document.querySelector<HTMLInputElement>("#symbol");
const periodSelect = document.querySelector<HTMLSelectElement>("#period");

if (!output || !searchBtn || !historyBtn || !subscribeBtn || !unsubscribeBtn) {
  throw new Error("missing elements");
}

const readPeriod = (): Period => {
  const value = periodSelect?.value ?? "1m";
  if (value.endsWith("m")) {
    return { multiplier: Number(value.replace("m", "")), timespan: "minute" };
  }
  if (value === "1d") {
    return { multiplier: 1, timespan: "day" };
  }
  throw new Error("unsupported period");
};

const append = (label: string, data: unknown) => {
  output.textContent += `\n${label}: ${JSON.stringify(data, null, 2)}`;
};

let barCount = 0;
let lastBarTs = 0;

const updateBarStatus = () => {
  if (!barStatus) {
    return;
  }
  const last = lastBarTs ? new Date(lastBarTs).toLocaleString() : "-";
  barStatus.textContent = `Bars: ${barCount}, last: ${last}`;
};

const updateWsStatus = (status: string) => {
  if (!wsStatus) {
    return;
  }
  wsStatus.textContent = `WS: ${status}`;
};

let datafeed = createAkshareGatewayDatafeed({
  baseUrl: baseUrlInput?.value ?? "",
  onWsStatus: (status) => updateWsStatus(status),
});

const toDateString = (ts: number) => {
  const dt = new Date(ts);
  return dt.toISOString().slice(0, 10);
};

const createProDatafeed = (baseUrl: string): ProDatafeed => {
  const datafeed = createAkshareGatewayDatafeed({
    baseUrl,
    onWsStatus: (status) => updateWsStatus(status),
  });
  return {
    async searchSymbols(search?: string) {
      const items = await datafeed.searchSymbols(search ?? "");
      return items.map((item) => ({
        ticker: item.symbol,
        shortName: item.symbol,
        name: item.name,
        exchange: item.exchange,
        market: item.exchange,
        priceCurrency: item.currency,
      }));
    },
    async getHistoryKLineData(symbol: ProSymbolInfo, period: ProPeriod, from: number, to: number) {
  const useDate = ["day", "week", "month"].includes(period.timespan);
  const fromValue = useDate ? toDateString(from) : from;
  const toValue = useDate ? toDateString(to) : to;
      const items = await datafeed.getHistoryKLineData(
        symbol.ticker,
        { multiplier: period.multiplier, timespan: period.timespan as Period["timespan"] },
        fromValue,
        toValue,
        500
      );
      return items.map((item) => ({
        timestamp: item.timestamp,
        open: item.open,
        high: item.high,
        low: item.low,
        close: item.close,
        volume: item.volume,
        turnover: item.amount ?? undefined,
      }));
    },
    subscribe(symbol: ProSymbolInfo, period: ProPeriod, callback) {
      datafeed.subscribe(
        symbol.ticker,
        { multiplier: period.multiplier, timespan: period.timespan as Period["timespan"] },
        (bar) => {
          callback({
            timestamp: bar.timestamp,
            open: bar.open,
            high: bar.high,
            low: bar.low,
            close: bar.close,
            volume: bar.volume,
            turnover: bar.amount ?? undefined,
          });
        }
      );
    },
    unsubscribe(symbol: ProSymbolInfo, period: ProPeriod) {
      datafeed.unsubscribe(symbol.ticker, {
        multiplier: period.multiplier,
        timespan: period.timespan as Period["timespan"],
      });
    },
  };
};

const chartContainer = document.querySelector<HTMLDivElement>("#chart");
if (!chartContainer) {
  throw new Error("missing chart container");
}

const chartPeriods: ProPeriod[] = [
  { multiplier: 1, timespan: "minute", text: "1m" },
  { multiplier: 5, timespan: "minute", text: "5m" },
  { multiplier: 15, timespan: "minute", text: "15m" },
  { multiplier: 30, timespan: "minute", text: "30m" },
  { multiplier: 60, timespan: "minute", text: "60m" },
  { multiplier: 1, timespan: "day", text: "D" },
  { multiplier: 1, timespan: "week", text: "W" },
  { multiplier: 1, timespan: "month", text: "M" },
];

const chinaStyles = {
  candle: {
    bar: {
      upColor: "#ef5350",
      downColor: "#26a69a",
      noChangeColor: "#9e9e9e",
      upBorderColor: "#ef5350",
      downBorderColor: "#26a69a",
      noChangeBorderColor: "#9e9e9e",
      upWickColor: "#ef5350",
      downWickColor: "#26a69a",
      noChangeWickColor: "#9e9e9e",
    },
  },
  indicator: {
    ohlc: {
      upColor: "#ef5350",
      downColor: "#26a69a",
      noChangeColor: "#9e9e9e",
    },
  },
};

let chart: KLineChartPro | null = null;

const createChart = (baseUrl: string) => {
  chartContainer.innerHTML = "";
  chart = new KLineChartPro({
    container: chartContainer,
    symbol: { ticker: defaultSymbol, name: defaultSymbol },
    period: chartPeriods[0],
    periods: chartPeriods,
    timezone: "Asia/Shanghai",
    styles: chinaStyles,
    datafeed: createProDatafeed(baseUrl),
  });
  if (klineStatus) {
    klineStatus.textContent = "KLineChart Pro: ready";
  }
};

createChart(baseUrlInput?.value ?? "");
let lastSubKey = "";

baseUrlInput?.addEventListener("change", () => {
  datafeed = createAkshareGatewayDatafeed({
    baseUrl: baseUrlInput.value,
    onWsStatus: (status) => updateWsStatus(status),
  });
  createChart(baseUrlInput.value);
});

searchBtn.addEventListener("click", async () => {
  output.textContent = "";
  const items = await datafeed.searchSymbols(symbolInput?.value ?? "");
  append("search", items);
});

historyBtn.addEventListener("click", async () => {
  output.textContent = "";
  const symbol = symbolInput?.value ?? defaultSymbol;
  const period = readPeriod();
  const now = Date.now();
  const useDate = ["day", "week", "month"].includes(period.timespan);
  const from = useDate ? now - 30 * 24 * 60 * 60 * 1000 : now - 60 * 60 * 1000;
  const queryFrom = useDate ? toDateString(from) : from;
  const queryTo = useDate ? toDateString(now) : now;
  const items = await datafeed.getHistoryKLineData(symbol, period, queryFrom, queryTo, 20);
  append("history", items);
});

const onBar = (bar: Bar) => {
  append("bar", bar);
  barCount += 1;
  lastBarTs = bar.timestamp;
  updateBarStatus();
};

subscribeBtn.addEventListener("click", () => {
  const symbol = symbolInput?.value ?? defaultSymbol;
  const period = readPeriod();
  lastSubKey = `${symbol}-${period.timespan}-${period.multiplier}`;
  datafeed.subscribe(symbol, period, onBar);
  append("subscribe", { symbol, period });
});

unsubscribeBtn.addEventListener("click", () => {
  const symbol = symbolInput?.value ?? defaultSymbol;
  const period = readPeriod();
  datafeed.unsubscribe(symbol, period);
  append("unsubscribe", { symbol, period, lastSubKey });
});

 
