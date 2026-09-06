"use client";

import { PageWrapper } from "@/components/layout/page-wrapper";
import { ConsensusGauge } from "@/components/dashboard/consensus-gauge";
import { AnalystGrid } from "@/components/dashboard/analyst-grid";
import { VoteBreakdown } from "@/components/dashboard/vote-breakdown";
import { ScannerHeatmap } from "@/components/dashboard/scanner-heatmap";
import { LegendaryModules } from "@/components/dashboard/legendary-modules";
import { QuickTrade } from "@/components/dashboard/quick-trade";
import { PriceChart } from "@/components/charts/price-chart";
import { Indicators } from "@/components/charts/indicators";
import { useTrades } from "@/hooks/use-trades";
import { usePositions } from "@/hooks/use-positions";
import { useSymbolStore } from "@/stores/symbol-store";

export default function DashboardPage() {
  const { selectedSymbol } = useSymbolStore();
  const { count: tradeCount } = useTrades();
  const { positions } = usePositions();

  return (
    <PageWrapper title="Dashboard" description="Overview of your trading intelligence">
      {/* Top stats */}
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

      {/* Main grid: analysis left, trade + chart right */}
      <div className="grid gap-4 lg:grid-cols-3">
        {/* Left column — consensus + analyst grid + vote breakdown */}
        <div className="space-y-4 lg:col-span-2">
          <div className="grid gap-4 sm:grid-cols-2">
            <ConsensusGauge />
            <div className="space-y-4">
              <AnalystGrid />
              <VoteBreakdown />
            </div>
          </div>

          {/* Scanner heatmap + legendary */}
          <div className="grid gap-4 sm:grid-cols-2">
            <ScannerHeatmap />
            <LegendaryModules />
          </div>
        </div>

        {/* Right column — quick trade + chart */}
        <div className="space-y-4">
          <QuickTrade />
          <PriceChart />
          <Indicators />
        </div>
      </div>
    </PageWrapper>
  );
}
