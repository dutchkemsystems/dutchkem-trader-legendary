"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Activity, RefreshCw, TrendingUp, TrendingDown } from "lucide-react";
import type { ScalperStatus } from "@/lib/types-v5";

interface ScalperDashboardPanelProps {
  status: ScalperStatus | null;
  loading: boolean;
}

function signalColor(signal: string): string {
  switch (signal?.toUpperCase()) {
    case "BUY":
      return "bg-green-500";
    case "SELL":
      return "bg-red-500";
    default:
      return "bg-gray-500";
  }
}

function signalBadgeVariant(signal: string): "success" | "destructive" | "secondary" {
  switch (signal?.toUpperCase()) {
    case "BUY":
      return "success";
    case "SELL":
      return "destructive";
    default:
      return "secondary";
  }
}

export function ScalperDashboardPanel({ status, loading }: ScalperDashboardPanelProps) {
  if (loading) {
    return (
      <Card className="col-span-full border-purple-500/20">
        <CardContent className="p-6">
          <div className="flex items-center justify-center text-muted-foreground">
            <RefreshCw className="h-4 w-4 animate-spin mr-2" />
            Loading scalper data...
          </div>
        </CardContent>
      </Card>
    );
  }

  if (!status || !status.enabled) {
    return (
      <Card className="col-span-full border-purple-500/20">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2 text-purple-400">
              <Activity className="h-5 w-5" />
              MTF Cascading Scalper
            </CardTitle>
            <Badge variant="secondary">DISABLED</Badge>
          </div>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground text-center py-4">
            MTF Cascading Scalper is disabled. Enable it in the engine config.
          </p>
        </CardContent>
      </Card>
    );
  }

  const profitColor =
    status.cumulative_profit >= 0 ? "text-green-400" : "text-red-400";

  return (
    <Card className="col-span-full border-purple-500/20">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-purple-400">
            <Activity className="h-5 w-5" />
            MTF Cascading Scalper
          </CardTitle>
          <div className="flex items-center gap-2">
            <Badge variant="success">ACTIVE</Badge>
            <span className="text-xs text-muted-foreground">
              Group {status.current_group}/{status.total_groups}
            </span>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* ΓòÉΓòÉΓòÉ STATS ROW ΓòÉΓòÉΓòÉ */}
        <div className="grid grid-cols-4 gap-4">
          <div className="p-3 rounded-lg bg-muted/50 text-center">
            <div className="text-xs text-muted-foreground">Total Trades</div>
            <div className="text-xl font-bold text-purple-400">
              {status.total_trades}
            </div>
          </div>
          <div className="p-3 rounded-lg bg-muted/50 text-center">
            <div className="text-xs text-muted-foreground">Win Rate</div>
            <div className="text-xl font-bold">{(status.win_rate * 100).toFixed(1)}%</div>
          </div>
          <div className="p-3 rounded-lg bg-muted/50 text-center">
            <div className="text-xs text-muted-foreground">Cumulative P&L</div>
            <div className={`text-xl font-bold ${profitColor}`}>
              {status.cumulative_profit >= 0 ? "+" : ""}
              ${status.cumulative_profit.toFixed(2)}
            </div>
          </div>
          <div className="p-3 rounded-lg bg-muted/50 text-center">
            <div className="text-xs text-muted-foreground">Active Trades</div>
            <div className="text-xl font-bold text-cyan-400">
              {status.active_trades.filter((t) => t.status === "open").length}
            </div>
          </div>
        </div>

        {/* ΓòÉΓòÉΓòÉ GROUP ALIGNMENT STATUS ΓòÉΓòÉΓòÉ */}
        <div>
          <div className="text-sm font-medium mb-2">Group Alignment</div>
          <div className="grid grid-cols-7 gap-2">
            {Object.entries(status.group_signals).map(([group, signal]) => (
              <div
                key={group}
                className="flex flex-col items-center gap-1 p-2 rounded-lg bg-muted/30"
              >
                <div
                  className={`h-3 w-3 rounded-full ${signalColor(signal)}`}
                  title={signal}
                />
                <span className="text-xs text-muted-foreground">{group}</span>
                <Badge
                  variant={signalBadgeVariant(signal)}
                  className="text-[10px] px-1"
                >
                  {signal?.toUpperCase() || "---"}
                </Badge>
              </div>
            ))}
          </div>
        </div>

        {/* ΓòÉΓòÉΓòÉ ACTIVE TRADES TABLE ΓòÉΓòÉΓòÉ */}
        {status.active_trades.length > 0 && (
          <div>
            <div className="text-sm font-medium mb-2">
              Active Trades ({status.active_trades.length})
            </div>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Ticket</TableHead>
                  <TableHead>Direction</TableHead>
                  <TableHead>Entry</TableHead>
                  <TableHead>Group</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">P&L</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {status.active_trades.map((trade) => (
                  <TableRow key={trade.ticket}>
                    <TableCell className="font-mono">{trade.ticket}</TableCell>
                    <TableCell>
                      <Badge
                        variant={trade.direction === "BUY" ? "success" : "destructive"}
                        className="flex items-center gap-1 w-fit"
                      >
                        {trade.direction === "BUY" ? (
                          <TrendingUp className="h-3 w-3" />
                        ) : (
                          <TrendingDown className="h-3 w-3" />
                        )}
                        {trade.direction}
                      </Badge>
                    </TableCell>
                    <TableCell className="font-mono">
                      {trade.entry_price.toFixed(5)}
                    </TableCell>
                    <TableCell>{trade.group}</TableCell>
                    <TableCell>
                      <Badge
                        variant={trade.status === "open" ? "default" : "secondary"}
                      >
                        {trade.status}
                      </Badge>
                    </TableCell>
                    <TableCell
                      className={`text-right font-mono ${
                        trade.pnl >= 0 ? "text-green-400" : "text-red-400"
                      }`}
                    >
                      {trade.pnl >= 0 ? "+" : ""}${trade.pnl.toFixed(2)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}

        {/* ΓòÉΓòÉΓòÉ LAST SCAN ΓòÉΓòÉΓòÉ */}
        <div className="text-xs text-muted-foreground text-center">
          Last scan: {status.last_scan}
        </div>
      </CardContent>
    </Card>
  );
}
