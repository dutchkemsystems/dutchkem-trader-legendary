"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { listTrades } from "@/lib/api";
import type { Trade } from "@/lib/types";

const POLL_INTERVAL = 30000;

export function useTrades() {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [count, setCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchTrades = useCallback(async () => {
    try {
      const result = await listTrades();
      setTrades(result.trades);
      setCount(result.count);
      setError(null);
    } catch (err) {
      // Silently handle timeout errors — don't block dashboard
      setError(err instanceof Error ? err.message : "Failed to fetch trades");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const delay = Math.random() * 2000;
    const timer = setTimeout(() => {
      fetchTrades();
      intervalRef.current = setInterval(fetchTrades, POLL_INTERVAL);
    }, delay);
    return () => {
      clearTimeout(timer);
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [fetchTrades]);

  return { trades, count, loading, error, refresh: fetchTrades };
}
