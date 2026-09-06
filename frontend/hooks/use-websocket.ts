"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { WSClient } from "@/lib/ws";
import { useMarketStore } from "@/stores/market-store";
import { useSymbolStore } from "@/stores/symbol-store";
import type { WebSocketMessage, MarketPrice } from "@/lib/types";

type ConnectionStatus = "connecting" | "connected" | "disconnected" | "error";

export function useWebSocket() {
  const [status, setStatus] = useState<ConnectionStatus>("disconnected");
  const [lastMessage, setLastMessage] = useState<WebSocketMessage | null>(null);
  const clientRef = useRef<WSClient | null>(null);
  const { updatePrice } = useMarketStore();
  const { selectedSymbol } = useSymbolStore();

  const connect = useCallback(() => {
    if (clientRef.current) return;

    const client = new WSClient("market");
    clientRef.current = client;

    client.subscribe("open", () => setStatus("connected"));
    client.subscribe("close", () => {
      setStatus("disconnected");
      clientRef.current = null;
    });
    client.subscribe("error", () => setStatus("error"));

    client.subscribe("market_price", (msg) => {
      setLastMessage(msg);
      if (msg.symbol && msg.data) {
        const data = msg.data as MarketPrice["data"];
        if (typeof data.price === "number") {
          updatePrice(msg.symbol, data.price);
        }
      }
    });

    setStatus("connecting");
    client.connect();
  }, [updatePrice]);

  const disconnect = useCallback(() => {
    clientRef.current?.disconnect();
    clientRef.current = null;
    setStatus("disconnected");
  }, []);

  useEffect(() => {
    return () => {
      clientRef.current?.disconnect();
      clientRef.current = null;
    };
  }, []);

  const send = useCallback((data: Record<string, unknown>) => {
    clientRef.current?.send(data);
  }, []);

  return { status, lastMessage, connect, disconnect, send };
}
