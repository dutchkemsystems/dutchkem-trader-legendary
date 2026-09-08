"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { DebateResult } from "@/lib/types-v5";

const WINNER_COLORS: Record<string, string> = {
  BULL: "text-emerald-400",
  BEAR: "text-red-400",
  NEUTRAL: "text-yellow-400",
};

const WINNER_BADGES: Record<string, "success" | "destructive" | "warning"> = {
  BULL: "success",
  BEAR: "destructive",
  NEUTRAL: "warning",
};

export function DebateResultCard({
  debate,
}: {
  debate: DebateResult | undefined;
}) {
  if (!debate || debate.error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Bull vs Bear Debate</CardTitle>
        </CardHeader>
        <CardContent className="flex items-center justify-center h-[120px]">
          <p className="text-sm text-muted-foreground">
            {debate?.error || "Run consensus with debate enabled"}
          </p>
        </CardContent>
      </Card>
    );
  }

  const bullPct = Math.round(debate.bull_confidence * 100);
  const bearPct = Math.round(debate.bear_confidence * 100);

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm">Bull vs Bear Debate</CardTitle>
          <Badge variant={WINNER_BADGES[debate.winner] || "default"}>
            {debate.winner}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Confidence comparison bar */}
        <div className="space-y-1">
          <div className="flex items-center justify-between text-sm">
            <span className="text-emerald-400 font-medium">
              🐂 Bull {bullPct}%
            </span>
            <span className="text-red-400 font-medium">
              {bearPct}% Bear 🐻
            </span>
          </div>
          <div className="h-3 w-full rounded-full bg-muted overflow-hidden flex">
            <div
              className="h-full bg-emerald-400 transition-all duration-500"
              style={{ width: `${bullPct}%` }}
            />
            <div
              className="h-full bg-red-400 transition-all duration-500"
              style={{ width: `${bearPct}%` }}
            />
          </div>
        </div>

        {/* Rounds */}
        <div className="flex items-center justify-between text-xs">
          <span className="text-muted-foreground">Rounds</span>
          <span className="font-mono">{debate.rounds}</span>
        </div>
      </CardContent>
    </Card>
  );
}
