import { PageWrapper } from "@/components/layout/page-wrapper";

export default function DashboardPage() {
  return (
    <PageWrapper title="Dashboard" description="Overview of your trading intelligence">
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-lg border border-border bg-card p-4">
          <p className="text-sm text-muted-foreground">Portfolio Value</p>
          <p className="text-2xl font-bold">$0.00</p>
        </div>
        <div className="rounded-lg border border-border bg-card p-4">
          <p className="text-sm text-muted-foreground">Open Positions</p>
          <p className="text-2xl font-bold">0</p>
        </div>
        <div className="rounded-lg border border-border bg-card p-4">
          <p className="text-sm text-muted-foreground">Win Rate</p>
          <p className="text-2xl font-bold">0%</p>
        </div>
        <div className="rounded-lg border border-border bg-card p-4">
          <p className="text-sm text-muted-foreground">Active Signals</p>
          <p className="text-2xl font-bold">0</p>
        </div>
      </div>
    </PageWrapper>
  );
}
