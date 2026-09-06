import { PageWrapper } from "@/components/layout/page-wrapper";
import { PositionsTable } from "@/components/portfolio/positions-table";
import { TradeHistory } from "@/components/portfolio/trade-history";
import { PnlChart } from "@/components/portfolio/pnl-chart";

export default function PortfolioPage() {
  return (
    <PageWrapper title="Portfolio" description="Track your positions and trades">
      <div className="space-y-6">
        <PnlChart />
        <div className="grid gap-6 lg:grid-cols-1">
          <PositionsTable />
          <TradeHistory />
        </div>
      </div>
    </PageWrapper>
  );
}
