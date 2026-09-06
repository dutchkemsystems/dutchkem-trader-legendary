"use client";

import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { AnalystResult, Signal } from "@/lib/types";

const DOT_COLORS: Record<Signal, string> = {
  BUY: "bg-emerald-400",
  SELL: "bg-red-400",
  HOLD: "bg-yellow-400",
};

interface AnalystDotProps {
  analyst: AnalystResult;
}

export function AnalystDot({ analyst }: AnalystDotProps) {
  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            className={cn(
              "h-8 w-8 rounded-full border-2 border-transparent transition-all hover:scale-110 hover:border-white/20 focus:outline-none focus:ring-2 focus:ring-white/20",
              DOT_COLORS[analyst.signal]
            )}
            aria-label={`${analyst.analyst_name}: ${analyst.signal}`}
          />
        </TooltipTrigger>
        <TooltipContent
          side="top"
          className="max-w-[240px] text-xs space-y-1.5"
        >
          <div className="flex items-center justify-between gap-2">
            <span className="font-medium text-white">
              {analyst.analyst_name}
            </span>
            <span
              className={cn(
                "font-bold",
                analyst.signal === "BUY"
                  ? "text-emerald-400"
                  : analyst.signal === "SELL"
                  ? "text-red-400"
                  : "text-yellow-400"
              )}
            >
              {analyst.signal}
            </span>
          </div>
          <div className="flex items-center gap-2 text-muted-foreground">
            <span>Confidence:</span>
            <span className="text-white">
              {Math.round(analyst.confidence * 100)}%
            </span>
          </div>
          {analyst.reasoning && (
            <p className="text-muted-foreground line-clamp-3">
              {analyst.reasoning}
            </p>
          )}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
