"use client";

import { useState, useMemo } from "react";
import { useAnalysts } from "@/hooks/use-analysts";
import { AnalystCard } from "./analyst-card";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { Signal } from "@/lib/types";
import { Filter, RotateCw } from "lucide-react";

type FilterType = "ALL" | Signal;

const FILTER_OPTIONS: { label: string; value: FilterType }[] = [
  { label: "All", value: "ALL" },
  { label: "Buy", value: "BUY" },
  { label: "Sell", value: "SELL" },
  { label: "Hold", value: "HOLD" },
];

const SIGNAL_COUNT_COLORS: Record<Signal, string> = {
  BUY: "text-emerald-400",
  SELL: "text-red-400",
  HOLD: "text-yellow-400",
};

export function AnalystsDeepDive() {
  const { resultsArray, loading, error, refresh } = useAnalysts();
  const [filter, setFilter] = useState<FilterType>("ALL");

  const filtered = useMemo(() => {
    if (filter === "ALL") return resultsArray;
    return resultsArray.filter((a) => a.signal === filter);
  }, [resultsArray, filter]);

  const signalCounts = useMemo(() => {
    const counts: Record<Signal, number> = { BUY: 0, SELL: 0, HOLD: 0 };
    for (const a of resultsArray) {
      counts[a.signal]++;
    }
    return counts;
  }, [resultsArray]);

  if (loading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Analyst Deep-Dive</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
          {Array.from({ length: 12 }).map((_, i) => (
            <Skeleton key={i} className="h-[140px] rounded-lg" />
          ))}
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Analyst Deep-Dive</CardTitle>
        </CardHeader>
        <CardContent className="flex items-center justify-center h-[120px]">
          <p className="text-sm text-destructive">{error}</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {/* Summary bar */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Filter className="h-4 w-4 text-muted-foreground" />
          <div className="flex gap-1.5">
            {FILTER_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                onClick={() => setFilter(opt.value)}
                className={cn(
                  "px-3 py-1 text-xs rounded-md transition-colors",
                  filter === opt.value
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted text-muted-foreground hover:bg-muted/80"
                )}
              >
                {opt.label}
                {opt.value !== "ALL" && (
                  <span className="ml-1 opacity-70">
                    {signalCounts[opt.value as Signal]}
                  </span>
                )}
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex gap-3 text-xs">
            {(Object.entries(signalCounts) as [Signal, number][]).map(
              ([sig, count]) => (
                <span key={sig} className={SIGNAL_COUNT_COLORS[sig]}>
                  {sig}: {count}
                </span>
              )
            )}
          </div>
          <button
            onClick={refresh}
            className="p-1.5 rounded-md hover:bg-muted transition-colors"
            title="Refresh analysts"
          >
            <RotateCw className="h-4 w-4 text-muted-foreground" />
          </button>
        </div>
      </div>

      {/* Cards grid */}
      {filtered.length === 0 ? (
        <Card>
          <CardContent className="flex items-center justify-center h-[120px]">
            <p className="text-sm text-muted-foreground">
              No analysts matching filter
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
          {filtered.map((analyst) => (
            <AnalystCard key={analyst.analyst_name} analyst={analyst} />
          ))}
        </div>
      )}
    </div>
  );
}
