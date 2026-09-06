export type Signal = "BUY" | "SELL" | "HOLD";

export type Timeframe =
  | "1M"
  | "5M"
  | "15M"
  | "1H"
  | "4H"
  | "1D";

export interface Candle {
  symbol: string;
  timeframe: Timeframe;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  timestamp: string;
}

export interface Tick {
  symbol: string;
  price: number;
  size: number;
  timestamp: string;
  exchange: string;
}

export interface Quote {
  symbol: string;
  bid: number;
  ask: number;
  bid_size: number;
  ask_size: number;
  timestamp: string;
}

export interface AnalystResult {
  analyst_name: string;
  symbol: string;
  timeframe: string;
  signal: Signal;
  confidence: number;
  reasoning: string;
  data: Record<string, unknown>;
  timestamp?: string;
}

export interface ConsensusResult {
  action: Signal;
  confidence: number;
  agreement_pct: number;
  reason: string;
  votes: Record<Signal, number>;
}

export interface TimeframeResult {
  timeframe: string;
  signal: Signal;
  confidence: number;
  data: Record<string, unknown>;
}

export interface ScanResult {
  symbol: string;
  timeframes: Record<string, TimeframeResult>;
  h1_bias: Signal;
  alignment: number;
  overall_signal: Signal;
  overall_confidence: number;
}

export interface SeykotaResult {
  trend: "BULLISH" | "BEARISH" | "NEUTRAL" | "CHOP";
  confidence: number;
  action: Signal;
  adx: number;
}

export interface TurtleSoupResult {
  signal: Signal;
  confidence: number;
  reason: string;
}

export interface PyramidingResult {
  add: boolean;
  additional_lot: number;
  reason: string;
}

export interface Trade {
  id: string;
  symbol: string;
  action: Signal;
  entry_price: number;
  stop_loss: number;
  take_profit: number;
  lot_size: number;
  status: "pending" | "open" | "closed";
}

export interface Position {
  id: string;
  symbol: string;
  action: Signal;
  entry_price: number;
  current_price: number;
  lot_size: number;
  unrealized_pnl: number;
  status: "open" | "closed";
}

export interface WatchlistItem {
  symbol: string;
  name: string;
  timeframe: Timeframe;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  token: string;
  user: string;
}

export interface WebSocketMessage {
  type: string;
  symbol?: string;
  data?: Record<string, unknown>;
  timestamp?: string;
}

export interface MarketPrice {
  symbol: string;
  signal: Signal;
  confidence: number;
  data: Record<string, unknown>;
}

export interface MarketAnalysis {
  symbol: string;
  timeframe: string;
  signal: Signal;
  confidence: number;
  reasoning: string;
  data: Record<string, unknown>;
}

export interface AnalystsResponse {
  analysts: string[];
  count: number;
}

export interface AnalystCapabilities {
  name: string;
  capabilities: string[];
}
