"use client";

import { useConsensus } from "@/hooks/use-consensus";
import { ConsensusGaugeSvg } from "@/components/visuals/consensus-gauge-svg";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { SIGNAL_COLORS } from "@/lib/constants";

export function ConsensusGauge() {
  const { consensus, loading, error } = useConsensus();

  if (loading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Consensus</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col items-center gap-3">
          <Skeleton className="h-[200px] w-[200px] rounded-full" />
          <Skeleton className="h-4 w-24" />
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Consensus</CardTitle>
        </CardHeader>
        <CardContent className="flex items-center justify-center h-[200px]">
          <p className="text-sm text-destructive">{error}</p>
        </CardContent>
      </Card>
    );
  }

  if (!consensus) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Consensus</CardTitle>
        </CardHeader>
        <CardContent className="flex items-center justify-center h-[200px]">
          <p className="text-sm text-muted-foreground">No data available</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm">Consensus</CardTitle>
          <Badge variant={consensus.action === "BUY" ? "success" : consensus.action === "SELL" ? "destructive" : "warning"}>
            {consensus.action}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col items-center gap-4">
        <ConsensusGaugeSvg
          agreement={consensus.agreement_pct}
          signal={consensus.action}
          confidence={consensus.confidence}
        />

        {consensus.reason && (
          <p className="text-xs text-muted-foreground text-center line-clamp-2 max-w-[220px]">
            {consensus.reason}
          </p>
        )}

        <div className="flex gap-3 text-xs">
          {(["BUY", "SELL", "HOLD"] as const).map((s) => (
            <div key={s} className="flex items-center gap-1">
              <span className={cn("h-2 w-2 rounded-full", SIGNAL_COLORS[s].replace("text-", "bg-"))} />
              <span className="text-muted-foreground">
                {s}: {consensus.votes[s]}
              </span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
