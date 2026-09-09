"use client";

import { useEffect, useState, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Activity,
  Play,
  Square,
  RefreshCw,
  Wifi,
  WifiOff,
  Monitor,
  Shield,
  Settings,
  Download,
  Key,
  CheckCircle2,
  XCircle,
  AlertTriangle,
} from "lucide-react";

const API = "http://localhost:8001/api/v1/live";

interface MT5Setup {
  installed: boolean;
  running: boolean;
  connected: boolean;
  path: string;
  has_credentials: boolean;
  needs_setup: boolean;
  setup_message: string;
}

interface AccountDetails {
  login: number;
  server: string;
  name: string;
  company: string;
  balance: number;
  equity: number;
  margin: number;
  margin_free: number;
  leverage: number;
  currency: string;
  profit: number;
  margin_level: number;
  account_type: string;
  positions_count: number;
  positions: any[];
  recent_deals: any[];
}

interface TradingState {
  active: boolean;
  control: string;
  state: {
    balance: number;
    consecutive_losses: number;
    week_number: number;
    total_trades: number;
    wins: number;
    losses: number;
    total_pnl: number;
    active_improvements: Record<string, boolean>;
    positions: Record<string, any>;
  };
  mt5: { installed: boolean; running: boolean; connected: boolean };
  account: AccountDetails | null;
  engine_pid: number | null;
}

const IMPROVEMENTS = [
  { name: "Correlation Filter", key: "correlation_filter", week: 1 },
  { name: "Dynamic Risk", key: "dynamic_risk", week: 1 },
  { name: "Spread Filter", key: "spread_filter", week: 1 },
  { name: "News Avoidance", key: "news_avoidance", week: 3 },
  { name: "Breakout Detection", key: "breakout_detection", week: 3 },
  { name: "Mean Reversion", key: "mean_reversion", week: 3 },
  { name: "Position Scaling", key: "position_scaling", week: 3 },
];

export function LiveTradingCard() {
  const [setup, setSetup] = useState<MT5Setup | null>(null);
  const [status, setStatus] = useState<TradingState | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [showConnect, setShowConnect] = useState(false);

  // Connect form
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [server, setServer] = useState("Exness-MT5Trial9");
  const [connectResult, setConnectResult] = useState<{ ok: boolean; msg: string } | null>(null);

  // Error feedback
  const [startError, setStartError] = useState<string | null>(null);

  const fetchSetup = useCallback(async () => {
    try {
      const res = await fetch(`${API}/setup`);
      if (res.ok) setSetup(await res.json());
    } catch (e) {
      console.error("Setup check failed:", e);
    }
  }, []);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API}/status`);
      if (res.ok) setStatus(await res.json());
    } catch (e) {
      console.error("Status check failed:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSetup();
    fetchStatus();
    const interval = setInterval(() => {
      fetchSetup();
      fetchStatus();
    }, 5000);
    return () => clearInterval(interval);
  }, [fetchSetup, fetchStatus]);

  // ─── Connect Handler ───
  const handleConnect = async () => {
    setActionLoading(true);
    setConnectResult(null);
    setStartError(null);
    try {
      const res = await fetch(`${API}/connect`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ login: parseInt(login), password, server }),
      });
      const data = await res.json();
      setConnectResult({ ok: data.success, msg: data.message });
      if (data.success) {
        setShowConnect(false);
        await fetchSetup();
        await fetchStatus();
      }
    } catch (e) {
      setConnectResult({ ok: false, msg: "Connection failed. Is the backend running?" });
    } finally {
      setActionLoading(false);
    }
  };

  // ─── Start Handler ───
  const handleStart = async () => {
    setActionLoading(true);
    setStartError(null);
    try {
      const res = await fetch(`${API}/start`, { method: "POST" });
      const data = await res.json();
      if (data.status === "error") {
        setStartError(data.message);
      }
      await fetchSetup();
      await fetchStatus();
    } catch (e) {
      setStartError("Failed to start. Is the backend running?");
    } finally {
      setActionLoading(false);
    }
  };

  // ─── Stop Handler ───
  const handleStop = async () => {
    setActionLoading(true);
    setStartError(null);
    try {
      await fetch(`${API}/stop`, { method: "POST" });
      await fetchStatus();
    } catch (e) {
      console.error("Stop failed:", e);
    } finally {
      setActionLoading(false);
    }
  };

  if (loading) {
    return (
      <Card className="col-span-full">
        <CardContent className="p-6">
          <div className="flex items-center justify-center text-muted-foreground">
            <RefreshCw className="h-4 w-4 animate-spin mr-2" />
            Loading trading engine...
          </div>
        </CardContent>
      </Card>
    );
  }

  const mt5 = setup || status?.mt5;
  const account = status?.account;
  const state = status?.state;
  const isActive = status?.active || false;
  const improvements = state?.active_improvements || {};
  const needsSetup = setup?.needs_setup ?? true;

  return (
    <Card className="col-span-full border-cyan-500/20">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-cyan-400">
            <Activity className="h-5 w-5" />
            Live Trading Engine
          </CardTitle>
          <div className="flex items-center gap-2">
            <Badge variant={isActive ? "default" : "secondary"} className={isActive ? "bg-green-500" : ""}>
              {isActive ? "ACTIVE" : "STOPPED"}
            </Badge>
            <Button size="sm" variant="outline" onClick={() => { fetchSetup(); fetchStatus(); }} disabled={actionLoading}>
              <RefreshCw className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">

        {/* ═══ MT5 STATUS ROW ═══ */}
        <div className="grid grid-cols-3 gap-4">
          <div className="flex items-center gap-2 p-3 rounded-lg bg-muted/50">
            <Monitor className={`h-4 w-4 ${mt5?.installed ? "text-green-400" : "text-red-400"}`} />
            <div>
              <div className="text-xs text-muted-foreground">MT5 Installed</div>
              <div className={`text-sm font-medium ${mt5?.installed ? "text-green-400" : "text-red-400"}`}>
                {mt5?.installed ? "Yes" : "No"}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2 p-3 rounded-lg bg-muted/50">
            <Activity className={`h-4 w-4 ${mt5?.running ? "text-green-400" : "text-red-400"}`} />
            <div>
              <div className="text-xs text-muted-foreground">Terminal</div>
              <div className={`text-sm font-medium ${mt5?.running ? "text-green-400" : "text-red-400"}`}>
                {mt5?.running ? "Running" : "Not Running"}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2 p-3 rounded-lg bg-muted/50">
            {mt5?.connected ? (
              <Wifi className="h-4 w-4 text-green-400" />
            ) : (
              <WifiOff className="h-4 w-4 text-red-400" />
            )}
            <div>
              <div className="text-xs text-muted-foreground">Broker</div>
              <div className={`text-sm font-medium ${mt5?.connected ? "text-green-400" : "text-red-400"}`}>
                {mt5?.connected ? "Connected" : "Disconnected"}
              </div>
            </div>
          </div>
        </div>

        {/* ═══ SETUP WIZARD (when MT5 not ready) ═══ */}
        {needsSetup && (
          <div className="p-5 rounded-xl bg-yellow-500/10 border border-yellow-500/20 space-y-4">
            <div className="flex items-start gap-3">
              <AlertTriangle className="h-5 w-5 text-yellow-400 mt-0.5 flex-shrink-0" />
              <div>
                <div className="font-medium text-yellow-300 mb-1">Setup Required</div>
                <div className="text-sm text-yellow-200/70">{setup?.setup_message || "Checking MT5 status..."}</div>
              </div>
            </div>

            {/* Step 1: Install */}
            {!mt5?.installed && (
              <div className="pl-8 space-y-2">
                <div className="text-sm font-medium text-white">Step 1: Install MetaTrader 5</div>
                <div className="text-xs text-gray-400">
                  Download from your broker (Exness) and install. Default path:
                  <code className="ml-1 text-cyan-400">C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe</code>
                </div>
                <a
                  href="https://www.exness.com/trading-platforms/"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-sm font-medium transition-colors"
                >
                  <Download className="h-4 w-4" />
                  Download MT5 from Exness
                </a>
              </div>
            )}

            {/* Step 2: Connect Account */}
            {mt5?.installed && !mt5?.connected && (
              <div className="pl-8 space-y-3">
                <div className="text-sm font-medium text-white">Step 2: Connect Your Account</div>

                {!showConnect ? (
                  <Button
                    onClick={() => setShowConnect(true)}
                    className="bg-cyan-600 hover:bg-cyan-700"
                  >
                    <Key className="h-4 w-4 mr-2" />
                    Enter MT5 Credentials
                  </Button>
                ) : (
                  <div className="p-4 rounded-lg bg-black/30 border border-white/10 space-y-3 max-w-md">
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="text-xs text-gray-400 mb-1 block">Login (Account #)</label>
                        <input
                          type="number"
                          value={login}
                          onChange={(e) => setLogin(e.target.value)}
                          placeholder="e.g. 476963617"
                          className="w-full px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-cyan-500/40"
                        />
                      </div>
                      <div>
                        <label className="text-xs text-gray-400 mb-1 block">Server</label>
                        <input
                          type="text"
                          value={server}
                          onChange={(e) => setServer(e.target.value)}
                          placeholder="e.g. Exness-MT5Trial9"
                          className="w-full px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-cyan-500/40"
                        />
                      </div>
                    </div>
                    <div>
                      <label className="text-xs text-gray-400 mb-1 block">Password</label>
                      <input
                        type="password"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        placeholder="Your MT5 password"
                        className="w-full px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-cyan-500/40"
                      />
                    </div>
                    <div className="flex gap-2">
                      <Button
                        onClick={handleConnect}
                        disabled={actionLoading || !login || !password}
                        className="bg-cyan-600 hover:bg-cyan-700"
                      >
                        {actionLoading ? (
                          <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                        ) : (
                          <CheckCircle2 className="h-4 w-4 mr-2" />
                        )}
                        Connect
                      </Button>
                      <Button variant="outline" onClick={() => setShowConnect(false)}>
                        Cancel
                      </Button>
                    </div>
                    {connectResult && (
                      <div className={`text-sm px-3 py-2 rounded-lg ${connectResult.ok ? "bg-green-500/15 text-green-400" : "bg-red-500/15 text-red-400"}`}>
                        {connectResult.msg}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* ═══ ACCOUNT DETAILS (when connected) ═══ */}
        {account && account.login && (
          <div className="grid grid-cols-4 gap-4">
            <div className="p-3 rounded-lg bg-muted/50">
              <div className="text-xs text-muted-foreground">Account</div>
              <div className="text-sm font-medium">{account.login}</div>
              <div className="text-xs text-muted-foreground">{account.server}</div>
            </div>
            <div className="p-3 rounded-lg bg-muted/50">
              <div className="text-xs text-muted-foreground">Balance</div>
              <div className="text-lg font-bold text-green-400">${account.balance?.toLocaleString()}</div>
            </div>
            <div className="p-3 rounded-lg bg-muted/50">
              <div className="text-xs text-muted-foreground">Equity</div>
              <div className="text-lg font-bold">${account.equity?.toLocaleString()}</div>
            </div>
            <div className="p-3 rounded-lg bg-muted/50">
              <div className="text-xs text-muted-foreground">Type</div>
              <Badge variant={account.account_type === "DEMO" ? "secondary" : "default"}
                className={account.account_type === "DEMO" ? "bg-yellow-500" : "bg-green-500"}>
                {account.account_type}
              </Badge>
            </div>
          </div>
        )}

        {/* ═══ PERFORMANCE STATS ═══ */}
        {state && (
          <div className="grid grid-cols-5 gap-4">
            <div className="p-3 rounded-lg bg-muted/50 text-center">
              <div className="text-xs text-muted-foreground">Trades</div>
              <div className="text-xl font-bold text-cyan-400">{state.total_trades || 0}</div>
            </div>
            <div className="p-3 rounded-lg bg-muted/50 text-center">
              <div className="text-xs text-muted-foreground">Wins</div>
              <div className="text-xl font-bold text-green-400">{state.wins || 0}</div>
            </div>
            <div className="p-3 rounded-lg bg-muted/50 text-center">
              <div className="text-xs text-muted-foreground">Losses</div>
              <div className="text-xl font-bold text-red-400">{state.losses || 0}</div>
            </div>
            <div className="p-3 rounded-lg bg-muted/50 text-center">
              <div className="text-xs text-muted-foreground">Win Rate</div>
              <div className="text-xl font-bold">
                {state.total_trades > 0 ? ((state.wins / state.total_trades) * 100).toFixed(1) : 0}%
              </div>
            </div>
            <div className="p-3 rounded-lg bg-muted/50 text-center">
              <div className="text-xs text-muted-foreground">P&L</div>
              <div className={`text-xl font-bold ${(state.total_pnl || 0) >= 0 ? "text-green-400" : "text-red-400"}`}>
                ${(state.total_pnl || 0) >= 0 ? "+" : ""}{(state.total_pnl || 0).toFixed(2)}
              </div>
            </div>
          </div>
        )}

        {/* ═══ IMPROVEMENTS ═══ */}
        <div>
          <div className="text-sm font-medium mb-2 flex items-center gap-2">
            <Shield className="h-4 w-4 text-cyan-400" />
            Improvements (Week {state?.week_number || 1})
          </div>
          <div className="grid grid-cols-4 gap-2">
            {IMPROVEMENTS.map((imp) => (
              <div
                key={imp.key}
                className={`p-2 rounded-lg text-center text-xs ${
                  improvements[imp.key]
                    ? "bg-green-500/20 text-green-400 border border-green-500/30"
                    : imp.week > 1
                    ? "bg-yellow-500/10 text-yellow-400 border border-yellow-500/20"
                    : "bg-muted/30 text-muted-foreground"
                }`}
              >
                <div className="font-medium">{imp.name}</div>
                <div className="opacity-70">{improvements[imp.key] ? "ACTIVE" : `Week ${imp.week}`}</div>
              </div>
            ))}
          </div>
        </div>

        {/* ═══ ERROR FEEDBACK ═══ */}
        {startError && (
          <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-sm text-red-400 flex items-center gap-2">
            <XCircle className="h-4 w-4 flex-shrink-0" />
            {startError}
          </div>
        )}

        {/* ═══ CONTROL BUTTONS ═══ */}
        <div className="flex gap-4 pt-2">
          <Button
            className="flex-1 bg-green-600 hover:bg-green-700"
            onClick={handleStart}
            disabled={isActive || actionLoading || needsSetup}
          >
            {actionLoading && !isActive ? (
              <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <Play className="h-4 w-4 mr-2" />
            )}
            Start Trading
          </Button>
          <Button
            className="flex-1 bg-red-600 hover:bg-red-700"
            onClick={handleStop}
            disabled={!isActive || actionLoading}
          >
            <Square className="h-4 w-4 mr-2" />
            Stop Trading
          </Button>
        </div>

        {/* ═══ ENGINE PID ═══ */}
        {status?.engine_pid && (
          <div className="text-xs text-muted-foreground text-center">
            Engine PID: {status.engine_pid} | Control: {status.control}
          </div>
        )}

        {/* ═══ OPEN POSITIONS ═══ */}
        {account?.positions && account.positions.length > 0 && (
          <div>
            <div className="text-sm font-medium mb-2">Open Positions ({account.positions.length})</div>
            <div className="space-y-1">
              {account.positions.map((pos: any) => (
                <div key={pos.ticket} className="flex items-center justify-between p-2 rounded bg-muted/30 text-xs">
                  <span className="font-medium">{pos.symbol}</span>
                  <Badge variant={pos.type === "BUY" ? "default" : "destructive"}
                    className={pos.type === "BUY" ? "bg-green-500" : ""}>
                    {pos.type}
                  </Badge>
                  <span>{pos.volume} lots</span>
                  <span>${pos.price_open?.toFixed(5)}</span>
                  <span className={pos.profit >= 0 ? "text-green-400" : "text-red-400"}>
                    ${pos.profit?.toFixed(2)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ═══ CONNECTED SUCCESS MESSAGE ═══ */}
        {!needsSetup && !isActive && (
          <div className="p-3 rounded-lg bg-green-500/10 border border-green-500/20 text-sm text-green-400 flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4" />
            MT5 connected. Ready to start trading!
          </div>
        )}
      </CardContent>
    </Card>
  );
}
