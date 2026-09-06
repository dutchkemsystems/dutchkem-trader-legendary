import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { Signal } from "@/lib/types";

const SIGNAL_VARIANT: Record<Signal, "success" | "destructive" | "warning"> = {
  BUY: "success",
  SELL: "destructive",
  HOLD: "warning",
};

interface SignalBadgeProps {
  signal: Signal;
  confidence?: number;
  className?: string;
}

export function SignalBadge({ signal, confidence, className }: SignalBadgeProps) {
  return (
    <Badge variant={SIGNAL_VARIANT[signal]} className={cn("text-xs", className)}>
      {signal}
      {confidence != null && (
        <span className="ml-1 opacity-70">{(confidence * 100).toFixed(0)}%</span>
      )}
    </Badge>
  );
}
