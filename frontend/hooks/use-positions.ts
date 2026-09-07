"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { API_BASE_URL } from "@/lib/constants";
import type { Position } from "@/lib/types";

const POLL_INTERVAL = 30000;

export function usePositions() {
  const [positions, setPositions] = useState<Position[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchPositions = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/positions/`, {
        headers: {
          Authorization: `Bearer ${typeof window !== "undefined" ? localStorage.getItem("token") || "" : ""}`,
          "Content-Type": "application/json",
        },
      });
      if (res.status === 401) {
        if (typeof window !== "undefined") {
          localStorage.removeItem("token");
          window.location.href = "/login";
        }
        return;
      }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setPositions(data.positions ?? data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch positions");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchPositions();
    intervalRef.current = setInterval(fetchPositions, POLL_INTERVAL);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [fetchPositions]);

  return { positions, loading, error, refresh: fetchPositions };
}
