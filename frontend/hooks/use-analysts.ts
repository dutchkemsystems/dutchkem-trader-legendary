"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { listAnalysts, analyze } from "@/lib/api";
import { useSymbolStore } from "@/stores/symbol-store";
import type { AnalystResult } from "@/lib/types";

const POLL_INTERVAL = 5000;
const STAGGER_CONCURRENCY = 3;
const STAGGER_DELAY_MS = 350;

export function useAnalysts() {
  const [results, setResults] = useState<Record<string, AnalystResult>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { selectedSymbol, selectedTimeframe } = useSymbolStore();
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchAll = useCallback(async () => {
    try {
      const { analysts } = await listAnalysts();
      const all: AnalystResult[] = [];

      for (let i = 0; i < analysts.length; i += STAGGER_CONCURRENCY) {
        const batch = analysts.slice(i, i + STAGGER_CONCURRENCY);
        const settled = await Promise.allSettled(
          batch.map((name) =>
            analyze(name, selectedSymbol, selectedTimeframe)
          )
        );
        for (const result of settled) {
          if (result.status === "fulfilled") {
            all.push(result.value);
          }
        }
        if (i + STAGGER_CONCURRENCY < analysts.length) {
          await new Promise((r) => setTimeout(r, STAGGER_DELAY_MS));
        }
      }

      const map: Record<string, AnalystResult> = {};
      for (const r of all) {
        map[r.analyst_name] = r;
      }
      setResults(map);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch analysts");
    } finally {
      setLoading(false);
    }
  }, [selectedSymbol, selectedTimeframe]);

  useEffect(() => {
    fetchAll();
    intervalRef.current = setInterval(fetchAll, POLL_INTERVAL);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [fetchAll]);

  const resultsArray = Object.values(results);

  return { results, resultsArray, loading, error, refresh: fetchAll };
}
