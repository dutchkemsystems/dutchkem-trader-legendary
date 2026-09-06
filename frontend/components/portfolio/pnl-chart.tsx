"use client";

import { useMemo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useTrades } from "@/hooks/use-trades";
import { cn } from "@/lib/utils";
import { RefreshCw } from "lucide-react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ReferenceLine,
} from "recharts";

export function PnlChart() {
  const { trades, loading, error, refresh } = useTrades();

  const chartData = useMemo(() => {
    const closedTrades = trades
      .filter((t) => t.status === "closed")
      .sort((a, b) => a.id.localeCompare(b.id));

    if (closedTrades.length === 0) return [];

    let cumulative = 0;
    return closedTrades.map((trade, i) => {
      const pnl =
        trade.action === "BUY"
          ? (trade.take_profit - trade.entry_price) * trade.lot_size
          : (trade.entry_price - trade.take_profit) * trade.lot_size;
      cumulative += pnl;
      return {
        index: i + 1,
        symbol: trade.symbol,
        pnl: Number(pnl.toFixed(2)),
        cumulative: Number(cumulative.toFixed(2)),
      };
    });
  }, [trades]);

  const totalPnl = chartData.length > 0 ? chartData[chartData.length - 1].cumulative : 0;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm">Cumulative P&L</CardTitle>
          <div className="flex items-center gap-2">
            <span
              className={cn(
                "font-mono text-sm font-medium",
                totalPnl >= 0 ? "text-emerald-400" : "text-red-400"
              )}
            >
              {totalPnl >= 0 ? "+" : ""}
              {totalPnl.toFixed(2)}
            </span>
            <button
              onClick={refresh}
              className="rounded-md p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"
            >
              <RefreshCw className="h-4 w-4" />
            </button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {loading && (
          <div className="h-[250px] animate-pulse rounded bg-muted" />
        )}

        {error && (
          <p className="text-sm text-destructive">{error}</p>
        )}

        {!loading && !error && chartData.length === 0 && (
          <div className="flex h-[250px] items-center justify-center">
            <p className="text-sm text-muted-foreground">
              No closed trades to chart
            </p>
          </div>
        )}

        {!loading && !error && chartData.length > 0 && (
          <div className="h-[250px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData}>
                <defs>
                  <linearGradient id="pnlGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop
                      offset="5%"
                      stopColor={totalPnl >= 0 ? "#34d399" : "#f87171"}
                      stopOpacity={0.3}
                    />
                    <stop
                      offset="95%"
                      stopColor={totalPnl >= 0 ? "#34d399" : "#f87171"}
                      stopOpacity={0}
                    />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                <XAxis
                  dataKey="index"
                  tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                  axisLine={{ stroke: "hsl(var(--border))" }}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                  axisLine={{ stroke: "hsl(var(--border))" }}
                  tickLine={false}
                  tickFormatter={(v: number) => v.toFixed(0)}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "hsl(var(--card))",
                    border: "1px solid hsl(var(--border))",
                    borderRadius: "8px",
                    fontSize: "12px",
                  }}
                  formatter={(value, name) => {
                    const num = typeof value === "number" ? value : Number(value);
                    return [
                      `${num >= 0 ? "+" : ""}${num.toFixed(2)}`,
                      name === "cumulative" ? "Cumulative" : "Trade P&L",
                    ];
                  }}
                  labelFormatter={(label) => `Trade #${label}`}
                />
                <ReferenceLine y={0} stroke="hsl(var(--muted-foreground))" strokeDasharray="3 3" />
                <Area
                  type="monotone"
                  dataKey="cumulative"
                  stroke={totalPnl >= 0 ? "#34d399" : "#f87171"}
                  fill="url(#pnlGradient)"
                  strokeWidth={2}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
