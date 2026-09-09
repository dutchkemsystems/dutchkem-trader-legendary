import axios from "axios";
import type {
  LoginRequest,
  LoginResponse,
  AnalystResult,
  AnalystsResponse,
  AnalystCapabilities,
  ConsensusResult,
  ScanResult,
  SeykotaResult,
  TurtleSoupResult,
  PyramidingResult,
  MarketPrice,
  MarketAnalysis,
  Trade,
} from "./types";
import type {
  FullConsensusResult,
  DebateResult,
  MemorySituation,
  GateStatus,
} from "./types-v5";
import { API_BASE_URL } from "./constants";

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: { "Content-Type": "application/json" },
});

api.interceptors.request.use((config) => {
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      if (typeof window !== "undefined") {
        localStorage.removeItem("token");
        window.location.href = "/login";
      }
    }
    return Promise.reject(error);
  }
);

export async function login(data: LoginRequest): Promise<LoginResponse> {
  const res = await api.post<LoginResponse>("/auth/login", data);
  if (typeof window !== "undefined") {
    localStorage.setItem("token", res.data.token);
  }
  return res.data;
}

export async function getCurrentUser(): Promise<{ user: string }> {
  const res = await api.get<{ user: string }>("/auth/me");
  return res.data;
}

export async function listAnalysts(): Promise<AnalystsResponse> {
  const res = await api.get<AnalystsResponse>("/analysts/");
  return res.data;
}

export async function getAnalyst(
  name: string
): Promise<AnalystCapabilities> {
  const res = await api.get<AnalystCapabilities>(`/analysts/${name}`);
  return res.data;
}

export async function analyze(
  analystName: string,
  symbol: string,
  timeframe = "1H"
): Promise<AnalystResult> {
  const res = await api.get<AnalystResult>(
    `/analysts/${analystName}/analyze`,
    { params: { symbol, timeframe } }
  );
  return res.data;
}

export async function getConsensus(
  symbol: string,
  timeframe = "1H"
): Promise<ConsensusResult> {
  const res = await api.get<ConsensusResult>(`/consensus/${symbol}`, {
    params: { timeframe },
  });
  return res.data;
}

export async function scanSymbol(symbol: string): Promise<ScanResult> {
  const res = await api.get<ScanResult>(`/scanner/${symbol}`);
  return res.data;
}

export async function getSeykota(symbol: string): Promise<SeykotaResult> {
  const res = await api.get<SeykotaResult>(`/legendary/seykota/${symbol}`);
  return res.data;
}

export async function getTurtleSoup(
  symbol: string
): Promise<{ symbol: string; result: TurtleSoupResult | null }> {
  const res = await api.get<{ symbol: string; result: TurtleSoupResult | null }>(
    `/legendary/turtle-soup/${symbol}`
  );
  return res.data;
}

export async function getPyramiding(
  symbol: string
): Promise<{ symbol: string } & PyramidingResult> {
  const res = await api.get<{ symbol: string } & PyramidingResult>(
    `/legendary/pyramiding/${symbol}`
  );
  return res.data;
}

export async function getMarketPrice(
  symbol: string
): Promise<MarketPrice> {
  const res = await api.get<MarketPrice>(`/market/${symbol}/price`);
  return res.data;
}

export async function getMarketAnalysis(
  symbol: string,
  timeframe = "1H"
): Promise<MarketAnalysis> {
  const res = await api.get<MarketAnalysis>(`/market/${symbol}/analysis`, {
    params: { timeframe },
  });
  return res.data;
}

export async function listTrades(): Promise<{
  trades: Trade[];
  count: number;
}> {
  const res = await api.get<{ trades: Trade[]; count: number }>("/trades/");
  return res.data;
}

export async function createTrade(
  trade: Omit<Trade, "id" | "status">
): Promise<{ id: string; status: string; trade: Trade }> {
  const res = await api.post<{ id: string; status: string; trade: Trade }>(
    "/trades/",
    trade
  );
  return res.data;
}

// --- V5 Intelligence endpoints ---

export async function getFullConsensus(
  symbol: string,
  timeframe = "1H"
): Promise<FullConsensusResult> {
  const res = await api.get<FullConsensusResult>(
    `/consensus/${symbol}/full`,
    { params: { timeframe } }
  );
  return res.data;
}

export async function getDebate(
  symbol: string
): Promise<DebateResult> {
  const res = await api.get<DebateResult>(`/consensus/${symbol}/debate`);
  return res.data;
}

export async function getMemory(
  symbol: string,
  timeframe = "1H"
): Promise<{ symbol: string; similar_situations: MemorySituation[] }> {
  const res = await api.get(`/consensus/${symbol}/memory`, {
    params: { timeframe },
  });
  return res.data;
}

export async function getPaperTrades(): Promise<{
  trades: Record<string, unknown>[];
  count: number;
}> {
  const res = await api.get("/paper-trades");
  return res.data;
}

export async function getPaperTradesStats(): Promise<{
  total_trades: number;
  buys: number;
  sells: number;
  holds: number;
  symbols: Record<string, Record<string, number>>;
  last_trade: Record<string, unknown> | null;
}> {
  const res = await api.get("/paper-trades/stats");
  return res.data;
}

// ---------------------------------------------------------------------------
// Live Trading API
// ---------------------------------------------------------------------------

export async function getMT5Setup() {
  const res = await api.get("/live/setup");
  return res.data;
}

export async function connectMT5(data: { login: number; password: string; server: string; mt5_path?: string }) {
  const res = await api.post("/live/connect", data);
  return res.data;
}

export async function getLiveTradingStatus() {
  const res = await api.get("/live/status");
  return res.data;
}

export async function getMT5Status() {
  const res = await api.get("/live/mt5/status");
  return res.data;
}

export async function getLiveAccount() {
  const res = await api.get("/live/account");
  return res.data;
}

export async function startLiveTrading() {
  const res = await api.post("/live/start");
  return res.data;
}

export async function stopLiveTrading() {
  const res = await api.post("/live/stop");
  return res.data;
}

export async function getLiveImprovements() {
  const res = await api.get("/live/improvements");
  return res.data;
}

export async function getLivePositions() {
  const res = await api.get("/live/positions");
  return res.data;
}

export async function getLiveTrades() {
  const res = await api.get("/live/trades");
  return res.data;
}

export default api;
