"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { GateStatus } from "@/lib/types-v5";

const GATE_NAMES: Record<string, string> = {
  ml_model: "ML Model",
  llm_consensus: "LLM Consensus",
  sentiment: "Sentiment",
  technical: "Technical",
  edge: "Edge",
  regime: "Regime",
  liquidity: "Liquidity",
};

const GATE_ICONS: Record<string, string> = {
  ml_model: "\u2699\uFE0F",
  llm_consensus: "\uD83E\uDD16",
  sentiment: "\uD83D\uDCAC",
  technical: "\uD83D\uDCCA",
  edge: "\uD83C\uDFAF",
  regime: "\uD83C\uDF0D",
  liquidity: "\uD83D\uDCB0",
};

export function GateStatusCard({ gates }: { gates: GateStatus }) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm">7-Gate Consensus</CardTitle>
          <Badge variant={gates.trade_allowed ? "success" : "destructive"}>
            {gates.passed_count}/{gates.total_gates} PASS
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        {Object.entries(gates.gates).map(([key, gate]) => (
          <div key={key} className="flex items-center justify-between text-sm">
            <div className="flex items-center gap-2">
              <span>{GATE_ICONS[key] || "\u25CB"}</span>
              <span className="text-muted-foreground">
                {GATE_NAMES[key] || key}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground font-mono">
                {typeof gate.value === "number"
                  ? gate.value.toFixed(3)
                  : gate.value}
              </span>
              <span
                className={cn(
                  "h-2 w-2 rounded-full",
                  gate.passed ? "bg-emerald-400" : "bg-red-400"
                )}
              />
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
