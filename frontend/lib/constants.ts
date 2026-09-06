import type { Signal, Timeframe, WatchlistItem } from "./types";

export const WATCHLIST: WatchlistItem[] = [
  { symbol: "EURUSD", name: "Euro / US Dollar", timeframe: "1H" },
  { symbol: "GBPUSD", name: "British Pound / US Dollar", timeframe: "1H" },
  { symbol: "USDJPY", name: "US Dollar / Japanese Yen", timeframe: "1H" },
  { symbol: "AUDUSD", name: "Australian Dollar / US Dollar", timeframe: "1H" },
  { symbol: "USDCAD", name: "US Dollar / Canadian Dollar", timeframe: "1H" },
  { symbol: "XAUUSD", name: "Gold / US Dollar", timeframe: "1H" },
  { symbol: "BTCUSD", name: "Bitcoin / US Dollar", timeframe: "1H" },
  { symbol: "ETHUSD", name: "Ethereum / US Dollar", timeframe: "1H" },
  { symbol: "USDCHF", name: "US Dollar / Swiss Franc", timeframe: "1H" },
  { symbol: "NZDUSD", name: "New Zealand Dollar / US Dollar", timeframe: "1H" },
];

export const TIMEFRAMES: Timeframe[] = ["1M", "5M", "15M", "1H", "4H", "1D"];

export const SIGNAL_COLORS: Record<Signal, string> = {
  BUY: "text-emerald-400",
  SELL: "text-red-400",
  HOLD: "text-yellow-400",
};

export const SIGNAL_BG_COLORS: Record<Signal, string> = {
  BUY: "bg-emerald-400/10",
  SELL: "bg-red-400/10",
  HOLD: "bg-yellow-400/10",
};

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

export const WS_BASE_URL =
  process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000/ws";

export const RECONNECT_INTERVAL = 3000;
export const MAX_RECONNECT_ATTEMPTS = 10;
