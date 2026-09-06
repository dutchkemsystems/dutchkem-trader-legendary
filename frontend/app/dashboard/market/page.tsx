"use client";

import { PageWrapper } from "@/components/layout/page-wrapper";
import { PriceChart } from "@/components/charts/price-chart";
import { Indicators } from "@/components/charts/indicators";
import { ErrorBoundary } from "@/components/error-boundary";
import { useMarketData } from "@/hooks/use-market-data";
import { useSymbolStore } from "@/stores/symbol-store";
import { useMarketStore } from "@/stores/market-store";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { TIMEFRAMES } from "@/lib/constants";
import type { Timeframe } from "@/lib/types";

function QuoteSkeleton() {
  return (
    <Card>
      <CardHeader>
        <Skeleton className="h-4 w-32" />
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-2 gap-4">
          <Skeleton className="h-16" />
          <Skeleton className="h-16" />
        </div>
        <Skeleton className="h-4 w-full" />
      </CardContent>
    </Card>
  );
}

function QuoteDisplay() {
  const { price, loading, error } = useMarketData();
  const livePriceMap = useMarketStore((s) => s.livePrice);
  const { selectedSymbol } = useSymbolStore();
  const livePrice = livePriceMap[selectedSymbol];

  if (loading) return <QuoteSkeleton />;

  if (error || !price) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Quote</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-destructive">
            {error || "No quote data"}
          </p>
        </CardContent>
      </Card>
    );
  }

  const data = price.data as Record<string, unknown>;
  const bid = (data.bid as number) ?? livePrice ?? 0;
  const ask = (data.ask as number) ?? livePrice ?? 0;
  const spread = bid && ask ? ((ask - bid) / ask * 10000).toFixed(1) : "--";

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm">Quote — {selectedSymbol}</CardTitle>
          <Badge
            variant={
              price.signal === "BUY"
                ? "success"
                : price.signal === "SELL"
                ? "destructive"
                : "warning"
            }
          >
            {price.signal} ({Math.round(price.confidence * 100)}%)
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-2 gap-4">
          <div className="rounded-lg bg-emerald-400/5 border border-emerald-400/20 p-3 text-center">
            <p className="text-xs text-emerald-400 mb-1">BID</p>
            <p className="text-xl font-bold font-mono text-emerald-400">
              {bid.toFixed(5)}
            </p>
          </div>
          <div className="rounded-lg bg-red-400/5 border border-red-400/20 p-3 text-center">
            <p className="text-xs text-red-400 mb-1">ASK</p>
            <p className="text-xl font-bold font-mono text-red-400">
              {ask.toFixed(5)}
            </p>
          </div>
        </div>
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>
            Spread: <span className="font-mono text-foreground">{spread} pips</span>
          </span>
          <span>
            Last: <span className="font-mono text-foreground">{livePrice ? livePrice.toFixed(5) : "--"}</span>
          </span>
        </div>
      </CardContent>
    </Card>
  );
}

function TimeframeSelector() {
  const { selectedTimeframe, selectTimeframe } = useSymbolStore();

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Timeframe</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex gap-2">
          {TIMEFRAMES.map((tf) => (
            <button
              key={tf}
              onClick={() => selectTimeframe(tf as Timeframe)}
              className={cn(
                "px-3 py-1.5 rounded-md text-xs font-medium transition-colors",
                selectedTimeframe === tf
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted/50 text-muted-foreground hover:bg-muted hover:text-foreground"
              )}
            >
              {tf}
            </button>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function MarketLoadingSkeleton() {
  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-2">
        <div className="h-[120px] rounded-lg border border-border bg-card animate-pulse" />
        <div className="h-[120px] rounded-lg border border-border bg-card animate-pulse" />
      </div>
      <div className="h-[400px] rounded-lg border border-border bg-card animate-pulse" />
      <div className="space-y-4">
        <div className="h-[120px] rounded-lg border border-border bg-card animate-pulse" />
        <div className="h-[120px] rounded-lg border border-border bg-card animate-pulse" />
      </div>
    </div>
  );
}

export default function MarketPage() {
  const { loading } = useMarketData();

  return (
    <PageWrapper
      title="Market"
      description="Live market data and charts"
    >
      {loading ? (
        <MarketLoadingSkeleton />
      ) : (
        <div className="space-y-6">
          <div className="grid gap-4 md:grid-cols-2">
            <ErrorBoundary>
              <QuoteDisplay />
            </ErrorBoundary>
            <ErrorBoundary>
              <TimeframeSelector />
            </ErrorBoundary>
          </div>
          <ErrorBoundary>
            <PriceChart className="w-full" />
          </ErrorBoundary>
          <ErrorBoundary>
            <Indicators className="w-full" />
          </ErrorBoundary>
        </div>
      )}
    </PageWrapper>
  );
}
