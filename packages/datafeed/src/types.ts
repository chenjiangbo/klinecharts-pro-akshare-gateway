export type Timespan = "minute" | "day" | "week" | "month";

export type Period = {
  multiplier: number;
  timespan: Timespan;
};

export type SymbolInfo = {
  symbol: string;
  name: string;
  exchange: string;
  type: string;
  currency: string;
  timezone: string;
};

export type Bar = {
  timestamp: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  amount?: number | null;
  isClosed?: boolean;
};

export type Datafeed = {
  searchSymbols: (searchText: string, limit?: number) => Promise<SymbolInfo[]>;
  getHistoryKLineData: (
    symbol: string,
    period: Period,
    from: number | string,
    to: number | string,
    limit?: number
  ) => Promise<Bar[]>;
  subscribe: (
    symbol: string,
    period: Period,
    callback: (bar: Bar) => void
  ) => void;
  unsubscribe: (symbol: string, period: Period) => void;
};
