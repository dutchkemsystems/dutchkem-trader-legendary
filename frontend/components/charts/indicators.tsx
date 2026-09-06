"use client";

import { useEffect, useRef } from "react";
import { useMarketStore } from "@/stores/market-store";
import { useSymbolStore } from "@/stores/symbol-store";
import type { Candle } from "@/lib/types";
import type { IChartApi } from "lightweight-charts";

function computeRSI(candles: Candle[], period = 14): { time: string; value: number }[] {
  if (candles.length < period + 1) return [];
  const result: { time: string; value: number }[] = [];
  let gains = 0;
  let losses = 0;

  for (let i = 1; i <= period; i++) {
    const diff = candles[i].close - candles[i - 1].close;
    if (diff > 0) gains += diff;
    else losses -= diff;
  }

  let avgGain = gains / period;
  let avgLoss = losses / period;
  const rsi = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
  result.push({ time: candles[period].timestamp, value: rsi });

  for (let i = period + 1; i < candles.length; i++) {
    const diff = candles[i].close - candles[i - 1].close;
    const gain = diff > 0 ? diff : 0;
    const loss = diff < 0 ? -diff : 0;
    avgGain = (avgGain * (period - 1) + gain) / period;
    avgLoss = (avgLoss * (period - 1) + loss) / period;
    const val = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
    result.push({ time: candles[i].timestamp, value: Math.round(val * 100) / 100 });
  }
  return result;
}

function computeEMA(values: number[], period: number): number[] {
  const k = 2 / (period + 1);
  const result: number[] = [values[0]];
  for (let i = 1; i < values.length; i++) {
    result.push(values[i] * k + result[i - 1] * (1 - k));
  }
  return result;
}

function computeMACD(
  candles: Candle[],
  fastPeriod = 12,
  slowPeriod = 26,
  signalPeriod = 9
) {
  if (candles.length < slowPeriod + signalPeriod) return { macd: [], signal: [], histogram: [] };

  const closes = candles.map((c) => c.close);
  const fastEMA = computeEMA(closes, fastPeriod);
  const slowEMA = computeEMA(closes, slowPeriod);
  const macdLine = fastEMA.map((v, i) => v - slowEMA[i]);

  const signalLine = computeEMA(macdLine.slice(slowPeriod - 1), signalPeriod);
  const offset = slowPeriod - 1;

  const macd: { time: string; value: number }[] = [];
  const signal: { time: string; value: number }[] = [];
  const histogram: { time: string; value: number; color: string }[] = [];

  for (let i = 0; i < signalLine.length; i++) {
    const idx = offset + i;
    const macdVal = Math.round(macdLine[idx] * 10000) / 10000;
    const sigVal = Math.round(signalLine[i] * 10000) / 10000;
    const histVal = Math.round((macdVal - sigVal) * 10000) / 10000;
    const time = candles[idx].timestamp;

    macd.push({ time, value: macdVal });
    signal.push({ time, value: sigVal });
    histogram.push({
      time,
      value: histVal,
      color: histVal >= 0 ? "rgba(52, 211, 153, 0.7)" : "rgba(248, 113, 113, 0.7)",
    });
  }

  return { macd, signal, histogram };
}

function computeBollingerBands(
  candles: Candle[],
  period = 20,
  stdDev = 2
) {
  if (candles.length < period) return { upper: [], middle: [], lower: [] };

  const upper: { time: string; value: number }[] = [];
  const middle: { time: string; value: number }[] = [];
  const lower: { time: string; value: number }[] = [];

  for (let i = period - 1; i < candles.length; i++) {
    const slice = candles.slice(i - period + 1, i + 1).map((c) => c.close);
    const mean = slice.reduce((a, b) => a + b, 0) / period;
    const variance = slice.reduce((a, b) => a + (b - mean) ** 2, 0) / period;
    const std = Math.sqrt(variance);
    const time = candles[i].timestamp;

    middle.push({ time, value: Math.round(mean * 100000) / 100000 });
    upper.push({ time, value: Math.round((mean + stdDev * std) * 100000) / 100000 });
    lower.push({ time, value: Math.round((mean - stdDev * std) * 100000) / 100000 });
  }

  return { upper, middle, lower };
}

interface IndicatorsProps {
  className?: string;
  showRSI?: boolean;
  showMACD?: boolean;
  showBollinger?: boolean;
}

export function Indicators({
  className,
  showRSI = true,
  showMACD = true,
  showBollinger = true,
}: IndicatorsProps) {
  const rsiContainerRef = useRef<HTMLDivElement>(null);
  const macdContainerRef = useRef<HTMLDivElement>(null);
  const rsiChartRef = useRef<IChartApi | null>(null);
  const macdChartRef = useRef<IChartApi | null>(null);

  const candles = useMarketStore((s) => s.candles);
  const { selectedSymbol } = useSymbolStore();

  // RSI Chart
  useEffect(() => {
    if (!showRSI || !rsiContainerRef.current) return;
    let chart: IChartApi;
    let rsiSeries: any;

    import("lightweight-charts").then(({ createChart, LineSeries, ColorType }) => {
      if (!rsiContainerRef.current) return;

      chart = createChart(rsiContainerRef.current, {
        layout: {
          background: { type: ColorType.Solid, color: "#0f1117" },
          textColor: "#9ca3af",
          fontSize: 11,
        },
        grid: {
          vertLines: { color: "#1f2937" },
          horzLines: { color: "#1f2937" },
        },
        rightPriceScale: {
          borderColor: "#1f2937",
          scaleMargins: { top: 0.05, bottom: 0.05 },
        },
        timeScale: { visible: false },
        autoSize: true,
      });

      rsiSeries = chart.addSeries(LineSeries, {
        color: "#a78bfa",
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
      });

      // Overbought / oversold reference lines via separate series
      const overboughtSeries = chart.addSeries(LineSeries, {
        color: "rgba(248, 113, 113, 0.3)",
        lineWidth: 1,
        lineStyle: 2,
        priceLineVisible: false,
        lastValueVisible: false,
      });
      const oversoldSeries = chart.addSeries(LineSeries, {
        color: "rgba(52, 211, 153, 0.3)",
        lineWidth: 1,
        lineStyle: 2,
        priceLineVisible: false,
        lastValueVisible: false,
      });

      if (candles.length) {
        const rsiData = computeRSI(candles);
        rsiSeries.setData(rsiData as any);

        if (rsiData.length > 0) {
          const refLine = rsiData.map((d) => ({ time: d.time, value: 70 }));
          const refLineLow = rsiData.map((d) => ({ time: d.time, value: 30 }));
          overboughtSeries.setData(refLine as any);
          oversoldSeries.setData(refLineLow as any);
        }
        chart.timeScale().fitContent();
      }

      rsiChartRef.current = chart;
    });

    return () => {
      if (rsiChartRef.current) {
        rsiChartRef.current.remove();
        rsiChartRef.current = null;
      }
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showRSI]);

  // MACD Chart
  useEffect(() => {
    if (!showMACD || !macdContainerRef.current) return;
    let chart: IChartApi;

    import("lightweight-charts").then(({ createChart, LineSeries, HistogramSeries, ColorType }) => {
      if (!macdContainerRef.current) return;

      chart = createChart(macdContainerRef.current, {
        layout: {
          background: { type: ColorType.Solid, color: "#0f1117" },
          textColor: "#9ca3af",
          fontSize: 11,
        },
        grid: {
          vertLines: { color: "#1f2937" },
          horzLines: { color: "#1f2937" },
        },
        rightPriceScale: { borderColor: "#1f2937" },
        timeScale: { visible: false },
        autoSize: true,
      });

      const histSeries = chart.addSeries(HistogramSeries, {
        priceLineVisible: false,
        lastValueVisible: false,
      });
      const macdLineSeries = chart.addSeries(LineSeries, {
        color: "#60a5fa",
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
      });
      const signalLineSeries = chart.addSeries(LineSeries, {
        color: "#f59e0b",
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
      });

      if (candles.length) {
        const { macd, signal, histogram } = computeMACD(candles);
        histSeries.setData(histogram as any);
        macdLineSeries.setData(macd as any);
        signalLineSeries.setData(signal as any);
        chart.timeScale().fitContent();
      }

      macdChartRef.current = chart;
    });

    return () => {
      if (macdChartRef.current) {
        macdChartRef.current.remove();
        macdChartRef.current = null;
      }
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showMACD]);

  const rsiData = computeRSI(candles);
  const bbData = computeBollingerBands(candles);
  const macdData = computeMACD(candles);

  return (
    <div className={className}>
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-medium text-foreground">
          {selectedSymbol} — Indicators
        </h3>
        <div className="flex gap-3 text-xs text-muted-foreground">
          {showRSI && rsiData.length > 0 && (
            <span>
              RSI(14): <span className={rsiData[rsiData.length - 1].value > 70 ? "text-red-400" : rsiData[rsiData.length - 1].value < 30 ? "text-emerald-400" : "text-foreground"}>
                {rsiData[rsiData.length - 1].value.toFixed(1)}
              </span>
            </span>
          )}
          {showBollinger && bbData.middle.length > 0 && (
            <span>
              BB(20,2): <span className="text-sky-400">
                {bbData.middle[bbData.middle.length - 1].value.toFixed(5)}
              </span>
            </span>
          )}
          {showMACD && macdData.histogram.length > 0 && (
            <span>
              MACD: <span className={macdData.histogram[macdData.histogram.length - 1].value >= 0 ? "text-emerald-400" : "text-red-400"}>
              {macdData.histogram[macdData.histogram.length - 1].value.toFixed(4)}
              </span>
            </span>
          )}
        </div>
      </div>

      {/* Bollinger Bands - rendered as overlay info since they sit on the price chart */}
      {showBollinger && bbData.upper.length > 0 && (
        <div className="mb-3 rounded-lg border border-border bg-card p-3">
          <div className="flex items-center justify-between text-xs">
            <div className="flex items-center gap-4">
              <span className="text-sky-400">● Upper: {bbData.upper[bbData.upper.length - 1].value.toFixed(5)}</span>
              <span className="text-yellow-400">● Middle: {bbData.middle[bbData.middle.length - 1].value.toFixed(5)}</span>
              <span className="text-sky-400">● Lower: {bbData.lower[bbData.lower.length - 1].value.toFixed(5)}</span>
            </div>
            <span className="text-muted-foreground">BB Width: {((bbData.upper[bbData.upper.length - 1].value - bbData.lower[bbData.lower.length - 1].value) / bbData.middle[bbData.middle.length - 1].value * 100).toFixed(2)}%</span>
          </div>
        </div>
      )}

      {/* RSI Pane */}
      {showRSI && (
        <div className="mb-3">
          <div className="mb-1 flex items-center justify-between px-1">
            <span className="text-xs text-purple-400 font-medium">RSI (14)</span>
            <div className="flex gap-2 text-[10px] text-muted-foreground">
              <span className="text-red-400">Overbought 70</span>
              <span className="text-emerald-400">Oversold 30</span>
            </div>
          </div>
          <div
            ref={rsiContainerRef}
            className="w-full rounded-lg border border-border overflow-hidden"
            style={{ height: "120px" }}
          />
        </div>
      )}

      {/* MACD Pane */}
      {showMACD && (
        <div className="mb-3">
          <div className="mb-1 flex items-center justify-between px-1">
            <span className="text-xs text-blue-400 font-medium">MACD (12, 26, 9)</span>
            <div className="flex gap-3 text-[10px] text-muted-foreground">
              <span><span className="text-blue-400">●</span> MACD</span>
              <span><span className="text-yellow-400">●</span> Signal</span>
              <span>Histogram</span>
            </div>
          </div>
          <div
            ref={macdContainerRef}
            className="w-full rounded-lg border border-border overflow-hidden"
            style={{ height: "120px" }}
          />
        </div>
      )}

      {!candles.length && (
        <p className="text-xs text-muted-foreground text-center py-4">
          Waiting for candle data to compute indicators...
        </p>
      )}
    </div>
  );
}
