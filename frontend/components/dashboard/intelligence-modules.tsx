"use client";

import { useEffect } from "react";
import { useIntelligence } from "@/hooks/use-intelligence";
import { useSymbolStore } from "@/stores/symbol-store";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

const TREND_COLORS: Record<string, string> = {
  BULLISH: "text-emerald-400",
  BEARISH: "text-red-400",
  NEUTRAL: "text-yellow-400",
  CHOP: "text-orange-400",
};

const TREND_BADGE: Record<string, "success" | "destructive" | "warning" | "default"> = {
  BULLISH: "success",
  BEARISH: "destructive",
  NEUTRAL: "warning",
  CHOP: "default",
};

function SeykotaCard({
  trend,
  confidence,
  action,
  adx,
}: {
  trend: string;
  confidence: number;
  action: string;
  adx: number;
}) {
  const confPct = Math.round(confidence * 100);
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm">Seykota Trend</CardTitle>
          <Badge variant={TREND_BADGE[trend] ?? "default"}>{trend}</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">Action</span>
          <span
            className={cn(
              "font-medium",
              action === "BUY"
                ? "text-emerald-400"
                : action === "SELL"
                ? "text-red-400"
                : "text-yellow-400"
            )}
          >
            {action}
          </span>
        </div>
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">Confidence</span>
          <span className="font-medium">{confPct}%</span>
        </div>
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">ADX</span>
          <span className="font-medium">{adx.toFixed(1)}</span>
        </div>
      </CardContent>
    </Card>
  );
}

function TurtleSoupCard({
  signal,
  confidence,
  reason,
}: {
  signal: string;
  confidence: number;
  reason: string;
}) {
  const confPct = Math.round(confidence * 100);
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm">Turtle Soup</CardTitle>
          <Badge
            variant={
              signal === "BUY"
                ? "success"
                : signal === "SELL"
                ? "destructive"
                : "warning"
            }
          >
            {signal}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">Confidence</span>
          <span className="font-medium">{confPct}%</span>
        </div>
        {reason && (
          <p className="text-xs text-muted-foreground line-clamp-3">{reason}</p>
        )}
      </CardContent>
    </Card>
  );
}

function PyramidingCard({
  add,
  additionalLot,
  reason,
}: {
  add: boolean;
  additionalLot: number;
  reason: string;
}) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm">Pyramiding</CardTitle>
          <Badge variant={add ? "success" : "default"}>
            {add ? "ADD" : "HOLD"}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">Additional Lot</span>
          <span className="font-medium">{additionalLot}</span>
        </div>
        {reason && (
          <p className="text-xs text-muted-foreground line-clamp-3">{reason}</p>
        )}
      </CardContent>
    </Card>
  );
}

function LoadingSkeleton() {
  return (
    <div className="grid gap-4 md:grid-cols-3">
      {[1, 2, 3].map((i) => (
        <Card key={i}>
          <CardHeader>
            <Skeleton className="h-4 w-24" />
          </CardHeader>
          <CardContent className="space-y-2">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-4 w-1/2" />
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

export function IntelligenceModules() {
  const { seykota, turtleSoup, pyramiding, loading, error, fetch } = useIntelligence();
  const { selectedSymbol } = useSymbolStore();

  useEffect(() => {
    fetch();
  }, [fetch]);

  if (loading) {
    return (
      <div className="space-y-4">
        <h3 className="text-sm font-medium text-muted-foreground">
          Intelligence Modules
        </h3>
        <LoadingSkeleton />
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-4">
        <h3 className="text-sm font-medium text-muted-foreground">
          Intelligence Modules
        </h3>
        <div className="rounded-lg border border-border bg-card p-6">
          <p className="text-sm text-destructive">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-muted-foreground">
          Intelligence Modules
        </h3>
        <button
          onClick={() => fetch()}
          className="text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          Refresh
        </button>
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        {seykota ? (
          <SeykotaCard
            trend={seykota.trend}
            confidence={seykota.confidence}
            action={seykota.action}
            adx={seykota.adx}
          />
        ) : (
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Seykota Trend</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-xs text-muted-foreground">No data</p>
            </CardContent>
          </Card>
        )}

        {turtleSoup ? (
          <TurtleSoupCard
            signal={turtleSoup.signal}
            confidence={turtleSoup.confidence}
            reason={turtleSoup.reason}
          />
        ) : (
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Turtle Soup</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-xs text-muted-foreground">No data</p>
            </CardContent>
          </Card>
        )}

        {pyramiding ? (
          <PyramidingCard
            add={pyramiding.add}
            additionalLot={pyramiding.additional_lot}
            reason={pyramiding.reason}
          />
        ) : (
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Pyramiding</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-xs text-muted-foreground">No data</p>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
