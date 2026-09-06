import { create } from "zustand";
import { WATCHLIST } from "@/lib/constants";
import type { Timeframe } from "@/lib/types";

interface SymbolState {
  selectedSymbol: string;
  watchlist: typeof WATCHLIST;
  selectedTimeframe: Timeframe;
  selectSymbol: (symbol: string) => void;
  selectTimeframe: (timeframe: Timeframe) => void;
}

export const useSymbolStore = create<SymbolState>((set) => ({
  selectedSymbol: WATCHLIST[0].symbol,
  watchlist: WATCHLIST,
  selectedTimeframe: WATCHLIST[0].timeframe,
  selectSymbol: (symbol: string) => set({ selectedSymbol: symbol }),
  selectTimeframe: (timeframe: Timeframe) => set({ selectedTimeframe: timeframe }),
}));
