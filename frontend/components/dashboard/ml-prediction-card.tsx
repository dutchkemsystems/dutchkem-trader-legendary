"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

interface MLPredictionData {
  p_up: number;
  direction: string;
  model_name: string;
  features_used: number;
}

export function MLPredictionCard({ ml }: { ml: MLPredictionData | undefined }) {
  if (!ml) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">ML Prediction</CardTitle>
        </CardHeader>
        <CardContent className="flex items-center justify-center h-[120px]">
          <p className="text-sm text-muted-foreground">No ML model trained</p>
        </CardContent>
      </Card>
    );
  }

  const pUpPct = Math.round(ml.p_up * 100);
  const direction = ml.direction?.toUpperCase() || "UNKNOWN";

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm">ML Prediction</CardTitle>
          <Badge
            variant={
              direction === "UP"
                ? "success"
                : direction === "DOWN"
                ? "destructive"
                : "default"
            }
          >
            {direction}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Probability bar */}
        <div className="space-y-1">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">P(UP)</span>
            <span
              className={cn(
                "font-mono font-bold",
                ml.p_up >= 0.6
                  ? "text-emerald-400"
                  : ml.p_up <= 0.4
                  ? "text-red-400"
                  : "text-yellow-400"
              )}
            >
              {pUpPct}%
            </span>
          </div>
          <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
            <div
              className={cn(
                "h-full rounded-full transition-all duration-500",
                ml.p_up >= 0.6
                  ? "bg-emerald-400"
                  : ml.p_up <= 0.4
                  ? "bg-red-400"
                  : "bg-yellow-400"
              )}
              style={{ width: `${pUpPct}%` }}
            />
          </div>
        </div>

        {/* Details */}
        <div className="flex items-center justify-between text-xs">
          <span className="text-muted-foreground">Model</span>
          <span className="font-mono">{ml.model_name}</span>
        </div>
        <div className="flex items-center justify-between text-xs">
          <span className="text-muted-foreground">Features</span>
          <span className="font-mono">{ml.features_used}</span>
        </div>
      </CardContent>
    </Card>
  );
}
