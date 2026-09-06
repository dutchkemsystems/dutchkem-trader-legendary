"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { getConsensus } from "@/lib/api";
import { useSymbolStore } from "@/stores/symbol-store";
import type { ConsensusResult } from "@/lib/types";

const POLL_INTERVAL = 5000;

export function useConsensus() {
  const [consensus, setConsensus] = useState<ConsensusResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { selectedSymbol, selectedTimeframe } = useSymbolStore();
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchConsensus = useCallback(async () => {
    try {
      const result = await getConsensus(selectedSymbol, selectedTimeframe);
      setConsensus(result);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch consensus");
    } finally {
      setLoading(false);
    }
  }, [selectedSymbol, selectedTimeframe]);

  useEffect(() => {
    fetchConsensus();
    intervalRef.current = setInterval(fetchConsensus, POLL_INTERVAL);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [fetchConsensus]);

  return { consensus, loading, error, refresh: fetchConsensus };
}
