"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { getFullConsensus } from "@/lib/api";
import { useSymbolStore } from "@/stores/symbol-store";
import type { FullConsensusResult } from "@/lib/types-v5";

const POLL_INTERVAL = 8000;

export function useFullConsensus() {
  const [data, setData] = useState<FullConsensusResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { selectedSymbol, selectedTimeframe } = useSymbolStore();
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const result = await getFullConsensus(selectedSymbol, selectedTimeframe);
      setData(result);
      setError(null);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to fetch full consensus"
      );
    } finally {
      setLoading(false);
    }
  }, [selectedSymbol, selectedTimeframe]);

  useEffect(() => {
    fetchData();
    intervalRef.current = setInterval(fetchData, POLL_INTERVAL);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [fetchData]);

  return { data, loading, error, refresh: fetchData };
}
