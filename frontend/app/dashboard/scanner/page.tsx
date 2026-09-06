import { PageWrapper } from "@/components/layout/page-wrapper";
import { ScannerHeatmap } from "@/components/dashboard/scanner-heatmap";
import { LegendaryModules } from "@/components/dashboard/legendary-modules";

export default function ScannerPage() {
  return (
    <PageWrapper title="Scanner" description="Multi-timeframe market scanner">
      <div className="space-y-6">
        <ScannerHeatmap />
        <LegendaryModules />
      </div>
    </PageWrapper>
  );
}
