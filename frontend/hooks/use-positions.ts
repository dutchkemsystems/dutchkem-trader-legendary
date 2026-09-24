"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import api from "@/lib/api";
import type { Position } from "@/lib/types";

const POLL_INTERVAL = 30000;

export function usePositions() {
  const [positions, setPositions] = useState<Position[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchPositions = useCallback(async () => {
    try {
      const res = await api.get("/positions/");
      const data = res.data;
      setPositions(data.positions ?? data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch positions");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // Stagger initial load to avoid thundering herd
    const delay = Math.random() * 2000;
    const timer = setTimeout(() => {
      fetchPositions();
      intervalRef.current = setInterval(fetchPositions, POLL_INTERVAL);
    }, delay);
    return () => {
      clearTimeout(timer);
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [fetchPositions]);

  return { positions, loading, error, refresh: fetchPositions };
}
