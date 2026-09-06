import { create } from "zustand";
import type { Candle, Quote } from "@/lib/types";

interface MarketState {
  livePrice: Record<string, number>;
  candles: Candle[];
  quote: Quote | null;
  updatePrice: (symbol: string, price: number) => void;
  setCandles: (candles: Candle[]) => void;
  setQuote: (quote: Quote | null) => void;
}

export const useMarketStore = create<MarketState>((set) => ({
  livePrice: {},
  candles: [],
  quote: null,
  updatePrice: (symbol: string, price: number) =>
    set((state) => ({
      livePrice: { ...state.livePrice, [symbol]: price },
    })),
  setCandles: (candles: Candle[]) => set({ candles }),
  setQuote: (quote: Quote | null) => set({ quote }),
}));
