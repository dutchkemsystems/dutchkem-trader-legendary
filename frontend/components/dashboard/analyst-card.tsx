"use client";

import { useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { SignalBadge } from "@/components/visuals/signal-badge";
import { cn } from "@/lib/utils";
import type { AnalystResult } from "@/lib/types";
import { ChevronDown, ChevronUp } from "lucide-react";

const SIGNAL_BORDER: Record<string, string> = {
  BUY: "border-l-emerald-400",
  SELL: "border-l-red-400",
  HOLD: "border-l-yellow-400",
};

interface AnalystCardProps {
  analyst: AnalystResult;
}

export function AnalystCard({ analyst }: AnalystCardProps) {
  const [expanded, setExpanded] = useState(false);
  const confidencePct = Math.round(analyst.confidence * 100);

  return (
    <Card
      className={cn(
        "cursor-pointer border-l-4 transition-all hover:shadow-md",
        SIGNAL_BORDER[analyst.signal]
      )}
      onClick={() => setExpanded(!expanded)}
    >
      <CardContent className="p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-sm truncate">
            {analyst.analyst_name}
          </h3>
          {expanded ? (
            <ChevronUp className="h-4 w-4 text-muted-foreground shrink-0" />
          ) : (
            <ChevronDown className="h-4 w-4 text-muted-foreground shrink-0" />
          )}
        </div>

        <div className="flex items-center gap-2">
          <SignalBadge signal={analyst.signal} />
          <span className="text-xs text-muted-foreground">
            {confidencePct}%
          </span>
        </div>

        {/* Confidence bar */}
        <div className="w-full h-1.5 rounded-full bg-muted overflow-hidden">
          <div
            className={cn(
              "h-full rounded-full transition-all",
              analyst.signal === "BUY" && "bg-emerald-400",
              analyst.signal === "SELL" && "bg-red-400",
              analyst.signal === "HOLD" && "bg-yellow-400"
            )}
            style={{ width: `${confidencePct}%` }}
          />
        </div>

        {/* Reasoning preview (always visible, truncated) */}
        <p className="text-xs text-muted-foreground line-clamp-2 leading-relaxed">
          {analyst.reasoning || "No reasoning provided"}
        </p>

        {/* Expanded details */}
        {expanded && (
          <div className="pt-2 border-t border-border space-y-3">
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div>
                <span className="text-muted-foreground">Symbol</span>
                <p className="font-medium">{analyst.symbol}</p>
              </div>
              <div>
                <span className="text-muted-foreground">Timeframe</span>
                <p className="font-medium">{analyst.timeframe}</p>
              </div>
              <div>
                <span className="text-muted-foreground">Confidence</span>
                <p className="font-medium">{confidencePct}%</p>
              </div>
              {analyst.timestamp && (
                <div>
                  <span className="text-muted-foreground">Updated</span>
                  <p className="font-medium">
                    {new Date(analyst.timestamp).toLocaleTimeString()}
                  </p>
                </div>
              )}
            </div>

            {/* Full reasoning */}
            <div>
              <span className="text-xs text-muted-foreground">Reasoning</span>
              <p className="text-xs text-foreground mt-1 leading-relaxed">
                {analyst.reasoning || "No reasoning provided"}
              </p>
            </div>

            {/* Raw data (if available) */}
            {analyst.data && Object.keys(analyst.data).length > 0 && (
              <div>
                <span className="text-xs text-muted-foreground">Raw Data</span>
                <pre className="mt-1 text-[10px] text-muted-foreground bg-muted rounded p-2 overflow-x-auto">
                  {JSON.stringify(analyst.data, null, 2)}
                </pre>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
