"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { SignalBadge } from "@/components/visuals/signal-badge";
import { usePositions } from "@/hooks/use-positions";
import { formatPrice, formatNumber } from "@/lib/utils";
import { cn } from "@/lib/utils";
import { RefreshCw } from "lucide-react";

export function PositionsTable() {
  const { positions, loading, error, refresh } = usePositions();

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm">Open Positions</CardTitle>
          <button
            onClick={refresh}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
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

        {!loading && !error && positions.length === 0 && (
          <p className="py-8 text-center text-sm text-muted-foreground">
            No open positions
          </p>
        )}

        {!loading && !error && positions.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-muted-foreground">
                  <th className="pb-2 font-medium">Symbol</th>
                  <th className="pb-2 font-medium">Side</th>
                  <th className="pb-2 font-medium text-right">Qty</th>
                  <th className="pb-2 font-medium text-right">Entry</th>
                  <th className="pb-2 font-medium text-right">Current</th>
                  <th className="pb-2 font-medium text-right">P&L</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((pos) => (
                  <tr
                    key={pos.id}
                    className="border-b border-border/50 last:border-0"
                  >
                    <td className="py-2.5 font-mono font-medium">
                      {pos.symbol}
                    </td>
                    <td className="py-2.5">
                      <SignalBadge signal={pos.action} />
                    </td>
                    <td className="py-2.5 text-right font-mono">
                      {formatNumber(pos.lot_size, 2)}
                    </td>
                    <td className="py-2.5 text-right font-mono">
                      {formatPrice(pos.entry_price, pos.symbol)}
                    </td>
                    <td className="py-2.5 text-right font-mono">
                      {formatPrice(pos.current_price, pos.symbol)}
                    </td>
                    <td
                      className={cn(
                        "py-2.5 text-right font-mono font-medium",
                        pos.unrealized_pnl >= 0
                          ? "text-emerald-400"
                          : "text-red-400"
                      )}
                    >
                      {pos.unrealized_pnl >= 0 ? "+" : ""}
                      {formatPrice(pos.unrealized_pnl, pos.symbol)}
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
