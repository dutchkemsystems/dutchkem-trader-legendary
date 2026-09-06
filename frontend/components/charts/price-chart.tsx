"use client";

import { useEffect, useRef } from "react";
import { useMarketStore } from "@/stores/market-store";
import { useSymbolStore } from "@/stores/symbol-store";
import type { Candle } from "@/lib/types";
import type { IChartApi } from "lightweight-charts";

function candleToChartData(candle: Candle) {
  return {
    time: candle.timestamp,
    open: candle.open,
    high: candle.high,
    low: candle.low,
    close: candle.close,
  };
}

function volumeToChartData(candle: Candle) {
  return {
    time: candle.timestamp,
    value: candle.volume,
    color:
      candle.close >= candle.open
        ? "rgba(52, 211, 153, 0.3)"
        : "rgba(248, 113, 113, 0.3)",
  };
}

interface PriceChartProps {
  className?: string;
}

export function PriceChart({ className }: PriceChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<any>(null);
  const volumeSeriesRef = useRef<any>(null);

  const candles = useMarketStore((s) => s.candles);
  const { selectedSymbol } = useSymbolStore();

  useEffect(() => {
    if (!chartContainerRef.current) return;

    let chart: IChartApi;
    let candleSeries: any;
    let volumeSeries: any;

    import("lightweight-charts").then(
      ({ createChart, CandlestickSeries, HistogramSeries, ColorType }) => {
        if (!chartContainerRef.current) return;

        chart = createChart(chartContainerRef.current, {
          layout: {
            background: { type: ColorType.Solid, color: "#0f1117" },
            textColor: "#9ca3af",
            fontSize: 12,
          },
          grid: {
            vertLines: { color: "#1f2937" },
            horzLines: { color: "#1f2937" },
          },
          crosshair: {
            vertLine: { color: "#4b5563", width: 1, style: 2 },
            horzLine: { color: "#4b5563", width: 1, style: 2 },
          },
          rightPriceScale: {
            borderColor: "#1f2937",
            scaleMargins: { top: 0.1, bottom: 0.25 },
          },
          timeScale: {
            borderColor: "#1f2937",
            timeVisible: true,
            secondsVisible: false,
          },
          autoSize: true,
        });

        candleSeries = chart.addSeries(CandlestickSeries, {
          upColor: "#34d399",
          downColor: "#f87171",
          borderVisible: false,
          wickUpColor: "#34d399",
          wickDownColor: "#f87171",
        });

        volumeSeries = chart.addSeries(HistogramSeries, {
          priceFormat: { type: "volume" },
          priceScaleId: "volume",
        });
        chart.priceScale("volume").applyOptions({
          scaleMargins: { top: 0.8, bottom: 0 },
        });

        chartRef.current = chart;
        candleSeriesRef.current = candleSeries;
        volumeSeriesRef.current = volumeSeries;

        if (candles.length) {
          candleSeries.setData(candles.map(candleToChartData) as any);
          volumeSeries.setData(candles.map(volumeToChartData) as any);
          chart.timeScale().fitContent();
        }
      }
    );

    return () => {
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
        candleSeriesRef.current = null;
        volumeSeriesRef.current = null;
      }
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!candleSeriesRef.current || !candles.length) return;

    const chartData = candles.map(candleToChartData);
    const volData = candles.map(volumeToChartData);

    candleSeriesRef.current.setData(chartData as any);
    if (volumeSeriesRef.current) {
      volumeSeriesRef.current.setData(volData as any);
    }
    chartRef.current?.timeScale().fitContent();
  }, [candles]);

  return (
    <div className={className}>
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-medium text-foreground">
          {selectedSymbol} — Price Chart
        </h3>
        <span className="text-xs text-muted-foreground">
          {candles.length} candles
        </span>
      </div>
      <div className="relative w-full rounded-lg border border-border overflow-hidden" style={{ height: "400px" }}>
        <div ref={chartContainerRef} className="w-full h-full" />
        {!candles.length && (
          <div className="absolute inset-0 flex items-center justify-center bg-background/80">
            <p className="text-sm text-muted-foreground">Waiting for candle data...</p>
          </div>
        )}
      </div>
    </div>
  );
}
