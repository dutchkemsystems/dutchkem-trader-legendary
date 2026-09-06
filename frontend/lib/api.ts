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

export default api;
