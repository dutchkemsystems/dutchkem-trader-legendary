"use client";

import { useState, useCallback } from "react";
import { getSeykota, getTurtleSoup, getPyramiding } from "@/lib/api";
import { useSymbolStore } from "@/stores/symbol-store";
import type { SeykotaResult, TurtleSoupResult, PyramidingResult } from "@/lib/types";

interface LegendaryState {
  seykota: SeykotaResult | null;
  turtleSoup: TurtleSoupResult | null;
  pyramiding: PyramidingResult | null;
  loading: boolean;
  error: string | null;
}

export function useLegendary() {
  const [state, setState] = useState<LegendaryState>({
    seykota: null,
    turtleSoup: null,
    pyramiding: null,
    loading: false,
    error: null,
  });
  const { selectedSymbol } = useSymbolStore();

  const fetchAll = useCallback(async () => {
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const [seykotaRes, turtleRes, pyramidingRes] = await Promise.all([
        getSeykota(selectedSymbol),
        getTurtleSoup(selectedSymbol),
        getPyramiding(selectedSymbol),
      ]);
      setState({
        seykota: seykotaRes,
        turtleSoup: turtleRes.result,
        pyramiding: pyramidingRes,
        loading: false,
        error: null,
      });
    } catch (err) {
      setState((s) => ({
        ...s,
        loading: false,
        error: err instanceof Error ? err.message : "Failed to fetch legendary data",
      }));
    }
  }, [selectedSymbol]);

  return { ...state, fetch: fetchAll };
}
