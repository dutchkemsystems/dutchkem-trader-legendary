"use client";

import { PageWrapper } from "@/components/layout/page-wrapper";
import { ScannerHeatmap } from "@/components/dashboard/scanner-heatmap";
import { IntelligenceModules } from "@/components/dashboard/intelligence-modules";
import { ErrorBoundary } from "@/components/error-boundary";
import { useScanner } from "@/hooks/use-scanner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { SIGNAL_COLORS, TIMEFRAMES } from "@/lib/constants";

function TimeframeDetailSkeleton() {
  return (
    <Card>
      <CardHeader>
        <Skeleton className="h-4 w-32" />
      </CardHeader>
      <CardContent className="space-y-2">
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-3/4" />
        <Skeleton className="h-4 w-1/2" />
      </CardContent>
    </Card>
  );
}

function TimeframeDetails() {
  const { scan, loading, error } = useScanner();

  if (loading) {
    return (
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {TIMEFRAMES.map((tf) => (
          <TimeframeDetailSkeleton key={tf} />
        ))}
      </div>
    );
  }

  if (error || !scan) {
    return null;
  }

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
      {TIMEFRAMES.map((tf) => {
        const tfResult = scan.timeframes[tf];
        if (!tfResult) {
          return (
            <Card key={tf}>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm">{tf}</CardTitle>
                  <Badge variant="default">N/A</Badge>
                </div>
              </CardHeader>
              <CardContent>
                <p className="text-xs text-muted-foreground">
                  No data available
                </p>
              </CardContent>
            </Card>
          );
        }

        const confPct = Math.round(tfResult.confidence * 100);
        const data = tfResult.data as Record<string, unknown>;

        return (
          <Card key={tf}>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm">{tf}</CardTitle>
                <Badge
                  variant={
                    tfResult.signal === "BUY"
                      ? "success"
                      : tfResult.signal === "SELL"
                      ? "destructive"
                      : "warning"
                  }
                >
                  {tfResult.signal}
                </Badge>
              </div>
            </CardHeader>
            <CardContent className="space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">Confidence</span>
                <span className="font-medium">{confPct}%</span>
              </div>
              <div className="w-full bg-muted/30 rounded-full h-2">
                <div
                  className={cn(
                    "h-2 rounded-full transition-all",
                    tfResult.signal === "BUY"
                      ? "bg-emerald-400"
                      : tfResult.signal === "SELL"
                      ? "bg-red-400"
                      : "bg-yellow-400"
                  )}
                  style={{ width: `${confPct}%` }}
                />
              </div>
              {Object.entries(data).length > 0 && (
                <div className="pt-2 space-y-1">
                  {Object.entries(data).slice(0, 4).map(([key, value]) => (
                    <div
                      key={key}
                      className="flex items-center justify-between text-xs"
                    >
                      <span className="text-muted-foreground capitalize">
                        {key.replace(/_/g, " ")}
                      </span>
                      <span className="font-mono text-foreground">
                        {typeof value === "number"
                          ? value.toFixed(4)
                          : String(value)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}

function AlignmentBar() {
  const { scan, loading } = useScanner();

  if (loading || !scan) return null;

  const alignment = Math.round(scan.alignment * 100);

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm">Multi-Timeframe Alignment</CardTitle>
          <Badge
            variant={
              scan.overall_signal === "BUY"
                ? "success"
                : scan.overall_signal === "SELL"
                ? "destructive"
                : "warning"
            }
          >
            {scan.overall_signal} ({Math.round(scan.overall_confidence * 100)}%
            conf)
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-center gap-4">
          <span className="text-sm text-muted-foreground">Alignment</span>
          <div className="flex-1">
            <div className="w-full bg-muted/30 rounded-full h-3">
              <div
                className={cn(
                  "h-3 rounded-full transition-all",
                  alignment >= 70
                    ? "bg-emerald-400"
                    : alignment >= 40
                    ? "bg-yellow-400"
                    : "bg-red-400"
                )}
                style={{ width: `${alignment}%` }}
              />
            </div>
          </div>
          <span className="text-sm font-bold font-mono">{alignment}%</span>
        </div>
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>H1 Bias: {scan.h1_bias}</span>
          <span>
            Symbol: <span className="font-mono text-foreground">{scan.symbol}</span>
          </span>
        </div>
      </CardContent>
    </Card>
  );
}

export default function ScannerPage() {
  return (
    <PageWrapper title="Scanner" description="Multi-timeframe market scanner">
      <div className="space-y-6">
        <ErrorBoundary>
          <ScannerHeatmap />
        </ErrorBoundary>
        <ErrorBoundary>
          <AlignmentBar />
        </ErrorBoundary>
        <ErrorBoundary>
          <TimeframeDetails />
        </ErrorBoundary>
        <ErrorBoundary>
          <IntelligenceModules />
        </ErrorBoundary>
      </div>
    </PageWrapper>
  );
}
