"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { SignalBadge } from "@/components/visuals/signal-badge";
import { useTrades } from "@/hooks/use-trades";
import { formatPrice, formatNumber } from "@/lib/utils";
import { cn } from "@/lib/utils";
import { RefreshCw } from "lucide-react";

const STATUS_VARIANT: Record<string, "default" | "success" | "destructive" | "secondary" | "warning"> = {
  open: "success",
  closed: "secondary",
  pending: "warning",
};

export function TradeHistory() {
  const { trades, count, loading, error, refresh } = useTrades();

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm">Trade History</CardTitle>
          <div className="flex items-center gap-2">
            <Badge variant="secondary" className="text-xs">
              {count} total
            </Badge>
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
          <div className="space-y-2">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-10 animate-pulse rounded bg-muted" />
            ))}
          </div>
        )}

        {error && (
          <p className="text-sm text-destructive">{error}</p>
        )}

        {!loading && !error && trades.length === 0 && (
          <p className="py-8 text-center text-sm text-muted-foreground">
            No trades recorded yet
          </p>
        )}

        {!loading && !error && trades.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-muted-foreground">
                  <th className="pb-2 font-medium">Symbol</th>
                  <th className="pb-2 font-medium">Side</th>
                  <th className="pb-2 font-medium text-right">Entry</th>
                  <th className="pb-2 font-medium text-right">Qty</th>
                  <th className="pb-2 font-medium">Status</th>
                  <th className="pb-2 font-medium text-right">SL / TP</th>
                </tr>
              </thead>
              <tbody>
                {trades.map((trade) => (
                  <tr
                    key={trade.id}
                    className="border-b border-border/50 last:border-0"
                  >
                    <td className="py-2.5 font-mono font-medium">
                      {trade.symbol}
                    </td>
                    <td className="py-2.5">
                      <SignalBadge signal={trade.action} />
                    </td>
                    <td className="py-2.5 text-right font-mono">
                      {formatPrice(trade.entry_price, trade.symbol)}
                    </td>
                    <td className="py-2.5 text-right font-mono">
                      {formatNumber(trade.lot_size, 2)}
                    </td>
                    <td className="py-2.5">
                      <Badge variant={STATUS_VARIANT[trade.status] ?? "default"} className="text-xs capitalize">
                        {trade.status}
                      </Badge>
                    </td>
                    <td className="py-2.5 text-right font-mono text-xs text-muted-foreground">
                      {formatPrice(trade.stop_loss, trade.symbol)} / {formatPrice(trade.take_profit, trade.symbol)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
