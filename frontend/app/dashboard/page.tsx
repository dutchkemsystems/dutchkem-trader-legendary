"use client";

import { PageWrapper } from "@/components/layout/page-wrapper";
import { ConsensusGauge } from "@/components/dashboard/consensus-gauge";
import { AnalystGrid } from "@/components/dashboard/analyst-grid";
import { VoteBreakdown } from "@/components/dashboard/vote-breakdown";
import { ScannerHeatmap } from "@/components/dashboard/scanner-heatmap";
import { LegendaryModules } from "@/components/dashboard/legendary-modules";
import { QuickTrade } from "@/components/dashboard/quick-trade";
import { MLPredictionCard } from "@/components/dashboard/ml-prediction-card";
import { GateStatusCard } from "@/components/dashboard/gate-status-card";
import { DebateResultCard } from "@/components/dashboard/debate-result-card";
import { MemoryContextCard } from "@/components/dashboard/memory-context-card";
import { PaperTradingCard } from "@/components/dashboard/paper-trading-card";
import { LiveTradingCard } from "@/components/dashboard/live-trading-card";
import { PriceChart } from "@/components/charts/price-chart";
import { Indicators } from "@/components/charts/indicators";
import { ErrorBoundary } from "@/components/error-boundary";
import { useTrades } from "@/hooks/use-trades";
import { usePositions } from "@/hooks/use-positions";
import { useFullConsensus } from "@/hooks/use-full-consensus";
import { useSymbolStore } from "@/stores/symbol-store";

function StatsLoadingSkeleton() {
  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      {[1, 2, 3, 4].map((i) => (
        <div
          key={i}
          className="rounded-lg border border-border bg-card p-4 animate-pulse"
        >
          <div className="h-3 w-20 bg-muted rounded mb-2" />
          <div className="h-7 w-16 bg-muted rounded" />
        </div>
      ))}
    </div>
  );
}

export default function DashboardPage() {
  const { selectedSymbol } = useSymbolStore();
  const { count: tradeCount, loading: tradesLoading } = useTrades();
  const { positions, loading: positionsLoading } = usePositions();
  const { data: fullConsensus, loading: consensusLoading } = useFullConsensus();

  if (tradesLoading && positionsLoading) {
    return (
      <PageWrapper
        title="Dashboard"
        description="Overview of your trading intelligence"
      >
        <StatsLoadingSkeleton />
        <div className="grid gap-4 lg:grid-cols-3">
          <div className="lg:col-span-2 space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="h-[320px] rounded-lg border border-border bg-card animate-pulse" />
              <div className="space-y-4">
                <div className="h-[160px] rounded-lg border border-border bg-card animate-pulse" />
                <div className="h-[80px] rounded-lg border border-border bg-card animate-pulse" />
              </div>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="h-[200px] rounded-lg border border-border bg-card animate-pulse" />
              <div className="h-[200px] rounded-lg border border-border bg-card animate-pulse" />
            </div>
          </div>
          <div className="space-y-4">
            <div className="h-[400px] rounded-lg border border-border bg-card animate-pulse" />
            <div className="h-[400px] rounded-lg border border-border bg-card animate-pulse" />
            <div className="h-[280px] rounded-lg border border-border bg-card animate-pulse" />
          </div>
        </div>
      </PageWrapper>
    );
  }

  return (
    <PageWrapper
      title="Dashboard"
      description="Overview of your trading intelligence"
    >
      {/* Live Trading Engine - Full Width */}
      <ErrorBoundary>
        <LiveTradingCard />
      </ErrorBoundary>

      {/* Top stats */}
      <ErrorBoundary>
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <div className="rounded-lg border border-border bg-card p-4">
            <p className="text-sm text-muted-foreground">Selected Symbol</p>
            <p className="text-2xl font-bold font-mono">{selectedSymbol}</p>
          </div>
          <div className="rounded-lg border border-border bg-card p-4">
            <p className="text-sm text-muted-foreground">Open Positions</p>
            <p className="text-2xl font-bold">{positions.length}</p>
          </div>
          <div className="rounded-lg border border-border bg-card p-4">
            <p className="text-sm text-muted-foreground">Total Trades</p>
            <p className="text-2xl font-bold">{tradeCount}</p>
          </div>
          <div className="rounded-lg border border-border bg-card p-4">
            <p className="text-sm text-muted-foreground">Market</p>
            <p className="text-2xl font-bold">{selectedSymbol}</p>
          </div>
        </div>
      </ErrorBoundary>

      {/* Main grid: analysis left, trade + chart right */}
      <div className="grid gap-4 lg:grid-cols-3">
        {/* Left column — consensus + analyst grid + vote breakdown */}
        <div className="space-y-4 lg:col-span-2">
          <div className="grid gap-4 sm:grid-cols-2">
            <ErrorBoundary>
              <ConsensusGauge />
            </ErrorBoundary>
            <div className="space-y-4">
              <ErrorBoundary>
                <AnalystGrid />
              </ErrorBoundary>
              <ErrorBoundary>
                <VoteBreakdown />
              </ErrorBoundary>
            </div>
          </div>

          {/* Scanner heatmap + legendary */}
          <div className="grid gap-4 sm:grid-cols-2">
            <ErrorBoundary>
              <ScannerHeatmap />
            </ErrorBoundary>
            <ErrorBoundary>
              <LegendaryModules />
            </ErrorBoundary>
          </div>

          {/* V5 Intelligence: ML + Gates + Debate + Memory */}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <ErrorBoundary>
              <MLPredictionCard ml={fullConsensus?.gates?.gates?.ml_model ? {
                p_up: (fullConsensus.gates.gates.ml_model.value as number) || 0.5,
                direction: (fullConsensus.gates.gates.ml_model.value as number) >= 0.5 ? "UP" : "DOWN",
                model_name: "XGBoost",
                features_used: 10,
              } : undefined} />
            </ErrorBoundary>
            <ErrorBoundary>
              {fullConsensus?.gates && <GateStatusCard gates={fullConsensus.gates} />}
            </ErrorBoundary>
            <ErrorBoundary>
              <DebateResultCard debate={fullConsensus?.debate} />
            </ErrorBoundary>
            <ErrorBoundary>
              <MemoryContextCard situations={fullConsensus?.similar_situations} />
            </ErrorBoundary>
          </div>

          {/* Paper Trading Stats */}
          <div className="grid gap-4 sm:grid-cols-2">
            <ErrorBoundary>
              <PaperTradingCard />
            </ErrorBoundary>
          </div>
        </div>

        {/* Right column — quick trade + chart */}
        <div className="space-y-4">
          <ErrorBoundary>
            <QuickTrade />
          </ErrorBoundary>
          <ErrorBoundary>
            <PriceChart />
          </ErrorBoundary>
          <ErrorBoundary>
            <Indicators />
          </ErrorBoundary>
        </div>
      </div>
    </PageWrapper>
  );
}
