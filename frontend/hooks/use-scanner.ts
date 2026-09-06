"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { scanSymbol } from "@/lib/api";
import { useSymbolStore } from "@/stores/symbol-store";
import type { ScanResult } from "@/lib/types";

const POLL_INTERVAL = 10000;

export function useScanner() {
  const [scan, setScan] = useState<ScanResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { selectedSymbol } = useSymbolStore();
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchScan = useCallback(async () => {
    try {
      const result = await scanSymbol(selectedSymbol);
      setScan(result);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to scan symbol");
    } finally {
      setLoading(false);
    }
  }, [selectedSymbol]);

  useEffect(() => {
    fetchScan();
    intervalRef.current = setInterval(fetchScan, POLL_INTERVAL);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [fetchScan]);

  return { scan, loading, error, refresh: fetchScan };
}
