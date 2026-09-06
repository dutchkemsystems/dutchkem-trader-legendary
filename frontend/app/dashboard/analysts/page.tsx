import { PageWrapper } from "@/components/layout/page-wrapper";
import { AnalystsDeepDive } from "@/components/dashboard/analysts-deep-dive";

export default function AnalystsPage() {
  return (
    <PageWrapper
      title="Analysts Deep-Dive"
      description="13 legendary intelligence analysts with signal details and reasoning"
    >
      <AnalystsDeepDive />
    </PageWrapper>
  );
}
