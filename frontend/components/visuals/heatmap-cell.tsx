"use client";

import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { Signal } from "@/lib/types";

const SIGNAL_BASE_COLORS: Record<Signal, [string, string]> = {
  BUY: ["bg-emerald-500", "text-emerald-400"],
  SELL: ["bg-red-500", "text-red-400"],
  HOLD: ["bg-yellow-500", "text-yellow-400"],
};

const SIGNAL_BG_ACCENT: Record<Signal, string> = {
  BUY: "bg-emerald-400",
  SELL: "bg-red-400",
  HOLD: "bg-yellow-400",
};

interface HeatmapCellProps {
  timeframe: string;
  signal: Signal;
  confidence: number;
}

function getConfidenceOpacity(confidence: number): number {
  return 0.15 + Math.min(confidence, 1) * 0.85;
}

export function HeatmapCell({ timeframe, signal, confidence }: HeatmapCellProps) {
  const opacity = getConfidenceOpacity(confidence);
  const [bgClass, textClass] = SIGNAL_BASE_COLORS[signal];
  const confidencePct = Math.round(confidence * 100);

  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>
          <div
            className={cn(
              "relative flex flex-col items-center justify-center rounded-lg border border-white/10 p-3 transition-all hover:scale-105 hover:ring-2 hover:ring-white/20 cursor-default select-none min-h-[72px]",
              bgClass
            )}
            style={{ opacity }}
            role="cell"
            aria-label={`${timeframe}: ${signal}, ${confidencePct}% confidence`}
          >
            <span className="text-xs font-medium text-white/80">{timeframe}</span>
            <span className={cn("text-lg font-bold", textClass)}>{confidencePct}%</span>
          </div>
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-[200px] text-xs space-y-1">
          <div className="flex items-center justify-between gap-2">
            <span className="font-medium">{timeframe}</span>
            <span className={cn("font-bold", textClass)}>{signal}</span>
          </div>
          <div className="text-muted-foreground">
            Confidence: {confidencePct}%
          </div>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
