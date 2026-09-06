"use client";

import type { Signal } from "@/lib/types";

interface ConsensusGaugeSvgProps {
  agreement: number;
  signal: Signal;
  confidence: number;
  size?: number;
}

const SIGNAL_STROKE: Record<Signal, string> = {
  BUY: "#34d399",
  SELL: "#f87171",
  HOLD: "#facc15",
};

const SIGNAL_BG: Record<Signal, string> = {
  BUY: "#065f46",
  SELL: "#7f1d1d",
  HOLD: "#713f12",
};

export function ConsensusGaugeSvg({
  agreement,
  signal,
  confidence,
  size = 200,
}: ConsensusGaugeSvgProps) {
  const clamped = Math.max(0, Math.min(100, agreement));
  const strokeWidth = size * 0.08;
  const radius = (size - strokeWidth) / 2;
  const cx = size / 2;
  const cy = size / 2;
  const circumference = 2 * Math.PI * radius;

  const startAngle = -210;
  const endAngle = 30;
  const totalSweep = endAngle - startAngle;
  const fillRatio = clamped / 100;

  const strokeDasharray = circumference;
  const sweepLength = (totalSweep / 360) * circumference;
  const strokeDashoffset = sweepLength * (1 - fillRatio);

  const strokeColor = SIGNAL_STROKE[signal];
  const bgColor = SIGNAL_BG[signal] || SIGNAL_BG.HOLD;

  const confidencePct = Math.round(confidence * 100);

  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      className="drop-shadow-lg"
      role="img"
      aria-label={`Consensus: ${clamped.toFixed(0)}% agreement, ${signal}, ${confidencePct}% confidence`}
    >
      {/* Background arc */}
      <circle
        cx={cx}
        cy={cy}
        r={radius}
        fill="none"
        stroke={bgColor}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeDasharray={`${sweepLength} ${circumference - sweepLength}`}
        strokeDashoffset={0}
        transform={`rotate(${startAngle + 90} ${cx} ${cy})`}
        opacity={0.4}
      />

      {/* Filled arc */}
      <circle
        cx={cx}
        cy={cy}
        r={radius}
        fill="none"
        stroke={strokeColor}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeDasharray={`${sweepLength} ${circumference - sweepLength}`}
        strokeDashoffset={strokeDashoffset}
        transform={`rotate(${startAngle + 90} ${cx} ${cy})`}
        className="transition-all duration-700 ease-out"
      />

      {/* Center text */}
      <text
        x={cx}
        y={cy - size * 0.04}
        textAnchor="middle"
        dominantBaseline="central"
        className="fill-foreground"
        fontSize={size * 0.22}
        fontWeight="bold"
        fontFamily="inherit"
      >
        {clamped.toFixed(0)}%
      </text>

      {/* Signal label */}
      <text
        x={cx}
        y={cy + size * 0.14}
        textAnchor="middle"
        dominantBaseline="central"
        fill={strokeColor}
        fontSize={size * 0.1}
        fontWeight="600"
        fontFamily="inherit"
      >
        {signal}
      </text>

      {/* Confidence badge */}
      <text
        x={cx}
        y={cy + size * 0.24}
        textAnchor="middle"
        dominantBaseline="central"
        className="fill-muted-foreground"
        fontSize={size * 0.07}
        fontFamily="inherit"
      >
        {confidencePct}% confidence
      </text>
    </svg>
  );
}
