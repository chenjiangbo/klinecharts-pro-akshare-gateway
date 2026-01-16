import type { Datafeed } from "./types";
type DatafeedOptions = {
    baseUrl: string;
    wsUrl?: string;
    onWsStatus?: (status: "open" | "close" | "error" | "reconnect") => void;
};
export declare function createAkshareGatewayDatafeed(options: DatafeedOptions): Datafeed;
export type { Bar, Datafeed, Period, SymbolInfo } from "./types";
