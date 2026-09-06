"use client";

import { useScanner } from "@/hooks/use-scanner";
import { HeatmapCell } from "@/components/visuals/heatmap-cell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { SIGNAL_COLORS, TIMEFRAMES } from "@/lib/constants";
import type { Signal } from "@/lib/types";

const ORDERED_TIMEFRAMES = TIMEFRAMES;

export function ScannerHeatmap() {
  const { scan, loading, error } = useScanner();

  if (loading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Scanner Heatmap</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-6 gap-2">
          {ORDERED_TIMEFRAMES.map((tf) => (
            <Skeleton key={tf} className="h-[72px] rounded-lg" />
          ))}
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Scanner Heatmap</CardTitle>
        </CardHeader>
        <CardContent className="flex items-center justify-center h-[72px]">
          <p className="text-sm text-destructive">{error}</p>
        </CardContent>
      </Card>
    );
  }

  if (!scan) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Scanner Heatmap</CardTitle>
        </CardHeader>
        <CardContent className="flex items-center justify-center h-[72px]">
          <p className="text-sm text-muted-foreground">No scan data</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm">Scanner Heatmap</CardTitle>
          <div className="flex items-center gap-2">
            <Badge
              variant={
                scan.overall_signal === "BUY"
                  ? "success"
                  : scan.overall_signal === "SELL"
                  ? "destructive"
                  : "warning"
              }
            >
              {scan.overall_signal}
            </Badge>
            <span className="text-xs text-muted-foreground">
              {Math.round(scan.overall_confidence * 100)}% conf
            </span>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-6 gap-2">
          {ORDERED_TIMEFRAMES.map((tf) => {
            const tfResult = scan.timeframes[tf];
            if (!tfResult) {
              return (
                <div
                  key={tf}
                  className="flex flex-col items-center justify-center rounded-lg border border-white/10 bg-muted/20 p-3 min-h-[72px]"
                >
                  <span className="text-xs text-muted-foreground">{tf}</span>
                  <span className="text-xs text-muted-foreground">--</span>
                </div>
              );
            }
            return (
              <HeatmapCell
                key={tf}
                timeframe={tf}
                signal={tfResult.signal}
                confidence={tfResult.confidence}
              />
            );
          })}
        </div>
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>Alignment: {Math.round(scan.alignment * 100)}%</span>
          <div className="flex items-center gap-1">
            <span>H1 Bias:</span>
            <span className={cn("font-medium", SIGNAL_COLORS[scan.h1_bias])}>
              {scan.h1_bias}
            </span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
