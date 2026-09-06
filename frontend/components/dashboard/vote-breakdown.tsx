"use client";

import { useAnalysts } from "@/hooks/use-analysts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { Signal } from "@/lib/types";

const BAR_COLORS: Record<Signal, string> = {
  BUY: "bg-emerald-400",
  SELL: "bg-red-400",
  HOLD: "bg-yellow-400",
};

const LABEL_COLORS: Record<Signal, string> = {
  BUY: "text-emerald-400",
  SELL: "text-red-400",
  HOLD: "text-yellow-400",
};

export function VoteBreakdown() {
  const { resultsArray, loading, error } = useAnalysts();

  if (loading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Vote Breakdown</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <Skeleton className="h-6 w-full rounded-full" />
          <div className="flex justify-between">
            {(["BUY", "SELL", "HOLD"] as const).map((s) => (
              <Skeleton key={s} className="h-3 w-16" />
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Vote Breakdown</CardTitle>
        </CardHeader>
        <CardContent className="flex items-center justify-center h-[80px]">
          <p className="text-sm text-destructive">{error}</p>
        </CardContent>
      </Card>
    );
  }

  const counts: Record<Signal, number> = { BUY: 0, SELL: 0, HOLD: 0 };
  for (const a of resultsArray) {
    counts[a.signal]++;
  }
  const total = resultsArray.length || 1;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Vote Breakdown</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex h-6 w-full overflow-hidden rounded-full">
          {(["BUY", "SELL", "HOLD"] as const).map(
            (s) =>
              counts[s] > 0 && (
                <div
                  key={s}
                  className={cn("h-full transition-all", BAR_COLORS[s])}
                  style={{ width: `${(counts[s] / total) * 100}%` }}
                />
              )
          )}
        </div>

        <div className="flex justify-between text-xs">
          {(["BUY", "SELL", "HOLD"] as const).map((s) => (
            <div key={s} className="flex items-center gap-1.5">
              <span className={cn("h-2 w-2 rounded-full", BAR_COLORS[s])} />
              <span className={cn("font-medium", LABEL_COLORS[s])}>{s}</span>
              <span className="text-muted-foreground">({counts[s]})</span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
