"use client";

import { useState, useEffect, useCallback } from "react";
import { getMarketPrice, getMarketAnalysis } from "@/lib/api";
import { useMarketStore } from "@/stores/market-store";
import { useSymbolStore } from "@/stores/symbol-store";
import type { MarketPrice, MarketAnalysis, Timeframe } from "@/lib/types";

export function useMarketData() {
  const [price, setPrice] = useState<MarketPrice | null>(null);
  const [analysis, setAnalysis] = useState<MarketAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { selectedSymbol, selectedTimeframe } = useSymbolStore();
  const { updatePrice, setQuote } = useMarketStore();

  const fetchPrice = useCallback(async () => {
    try {
      const result = await getMarketPrice(selectedSymbol);
      setPrice(result);
      updatePrice(selectedSymbol, result.data.price as number);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch price");
    } finally {
      setLoading(false);
    }
  }, [selectedSymbol, updatePrice]);

  const fetchAnalysis = useCallback(
    async (tf?: Timeframe) => {
      try {
        const result = await getMarketAnalysis(selectedSymbol, tf ?? selectedTimeframe);
        setAnalysis(result);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to fetch analysis");
      }
    },
    [selectedSymbol, selectedTimeframe]
  );

  const fetchAll = useCallback(async () => {
    setLoading(true);
    await Promise.all([fetchPrice(), fetchAnalysis()]);
  }, [fetchPrice, fetchAnalysis]);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  return { price, analysis, loading, error, refresh: fetchAll, refreshPrice: fetchPrice, refreshAnalysis: fetchAnalysis };
}
