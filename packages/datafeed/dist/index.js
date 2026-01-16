export function createAkshareGatewayDatafeed(options) {
    const baseUrl = options.baseUrl.replace(/\/$/, "");
    const wsUrl = options.wsUrl ?? baseUrl.replace(/^http/, "ws");
    const subscriptions = new Map();
    let ws = null;
    let reconnectDelay = 1000;
    const ensureWs = () => {
        if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
            return;
        }
        options.onWsStatus?.("reconnect");
        ws = new WebSocket(`${wsUrl}/api/v1/ws`);
        ws.onopen = () => {
            reconnectDelay = 1000;
            options.onWsStatus?.("open");
            for (const key of subscriptions.keys()) {
                const [symbol, period] = key.split("|");
                ws?.send(JSON.stringify({ op: "subscribe", symbol, period }));
            }
        };
        ws.onmessage = (event) => {
            const payload = JSON.parse(event.data);
            if (payload.op !== "bar") {
                return;
            }
            const key = `${payload.symbol}|${payload.period}`;
            const sub = subscriptions.get(key);
            if (!sub) {
                return;
            }
            const bar = {
                timestamp: payload.bar.ts,
                open: payload.bar.open,
                high: payload.bar.high,
                low: payload.bar.low,
                close: payload.bar.close,
                volume: payload.bar.volume,
                amount: payload.bar.amount,
                isClosed: payload.bar.is_closed,
            };
            for (const cb of sub.callbacks) {
                cb(bar);
            }
        };
        ws.onclose = () => {
            options.onWsStatus?.("close");
            setTimeout(() => ensureWs(), reconnectDelay);
            reconnectDelay = Math.min(10000, reconnectDelay * 2);
        };
        ws.onerror = () => {
            options.onWsStatus?.("error");
        };
    };
    const toPeriodId = (period) => {
        if (period.timespan === "minute") {
            return `${period.multiplier}m`;
        }
        if (period.timespan === "day") {
            return "1d";
        }
        if (period.timespan === "week") {
            return "1w";
        }
        if (period.timespan === "month") {
            return "1M";
        }
        throw new Error("unsupported period");
    };
    const searchSymbols = async (searchText, limit = 20) => {
        if (!searchText) {
            return [];
        }
        const params = new URLSearchParams({ q: searchText, limit: String(limit) });
        const res = await fetch(`${baseUrl}/api/v1/symbols/search?${params}`);
        if (!res.ok) {
            throw new Error("search failed");
        }
        const data = (await res.json());
        return data.items;
    };
    const getHistoryKLineData = async (symbol, period, from, to, limit) => {
        const params = new URLSearchParams({
            symbol,
            period: toPeriodId(period),
            from: String(from),
            to: String(to),
        });
        if (limit) {
            params.set("limit", String(limit));
        }
        const res = await fetch(`${baseUrl}/api/v1/bars/history?${params}`);
        if (!res.ok) {
            throw new Error("history failed");
        }
        const data = (await res.json());
        return data.items.map((item) => ({
            timestamp: item.ts,
            open: item.open,
            high: item.high,
            low: item.low,
            close: item.close,
            volume: item.volume,
            amount: item.amount,
            isClosed: item.is_closed,
        }));
    };
    const subscribe = (symbol, period, callback) => {
        const periodId = toPeriodId(period);
        const key = `${symbol}|${periodId}`;
        const sub = subscriptions.get(key) ?? { callbacks: new Set() };
        sub.callbacks.add(callback);
        subscriptions.set(key, sub);
        ensureWs();
        if (ws?.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ op: "subscribe", symbol, period: periodId }));
        }
    };
    const unsubscribe = (symbol, period) => {
        const periodId = toPeriodId(period);
        const key = `${symbol}|${periodId}`;
        const sub = subscriptions.get(key);
        if (!sub) {
            return;
        }
        sub.callbacks.clear();
        subscriptions.delete(key);
        if (ws?.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ op: "unsubscribe", symbol, period: periodId }));
        }
    };
    return {
        searchSymbols,
        getHistoryKLineData,
        subscribe,
        unsubscribe,
    };
}
