"use client";

import { useEffect, useState } from "react";
import { getPaperTradesStats } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

interface PaperTradeStats {
  total_trades: number;
  buys: number;
  sells: number;
  holds: number;
  symbols: Record<string, Record<string, number>>;
  last_trade: Record<string, unknown> | null;
}

export function PaperTradingCard() {
  const [stats, setStats] = useState<PaperTradeStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const data = await getPaperTradesStats();
        setStats(data);
      } catch {
        // API not available yet
      } finally {
        setLoading(false);
      }
    };
    fetchStats();
    const interval = setInterval(fetchStats, 30000);
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Paper Trading</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-xs text-muted-foreground">Loading...</p>
        </CardContent>
      </Card>
    );
  }

  if (!stats || stats.total_trades === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Paper Trading</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <p className="text-xs text-muted-foreground">No trades yet</p>
          <p className="text-[10px] text-muted-foreground">
            Run paper_trading.py to start generating decisions
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm">Paper Trading</CardTitle>
          <Badge variant="default">{stats.total_trades} trades</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Action breakdown */}
        <div className="flex items-center justify-between text-sm">
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-emerald-400" />
            <span className="text-muted-foreground">Buy</span>
          </div>
          <span className="font-mono">{stats.buys}</span>
        </div>
        <div className="flex items-center justify-between text-sm">
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-red-400" />
            <span className="text-muted-foreground">Sell</span>
          </div>
          <span className="font-mono">{stats.sells}</span>
        </div>
        <div className="flex items-center justify-between text-sm">
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-yellow-400" />
            <span className="text-muted-foreground">Hold</span>
          </div>
          <span className="font-mono">{stats.holds}</span>
        </div>

        {/* Per-symbol breakdown */}
        {Object.entries(stats.symbols).map(([sym, data]) => (
          <div key={sym} className="rounded-md border border-border p-2 space-y-1">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium">{sym}</span>
              <span className="text-[10px] text-muted-foreground font-mono">
                {data.buy}B / {data.sell}S / {data.hold}H
              </span>
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
