"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { SignalBadge } from "@/components/visuals/signal-badge";
import { useSymbolStore } from "@/stores/symbol-store";
import { useMarketStore } from "@/stores/market-store";
import { createTrade } from "@/lib/api";
import { formatPrice } from "@/lib/utils";
import type { Signal } from "@/lib/types";

export function QuickTrade() {
  const { selectedSymbol } = useSymbolStore();
  const { quote } = useMarketStore();

  const [action, setAction] = useState<Signal>("BUY");
  const [stopLoss, setStopLoss] = useState("");
  const [takeProfit, setTakeProfit] = useState("");
  const [lotSize, setLotSize] = useState("");
  const [showConfirm, setShowConfirm] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<{ id: string; status: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const entryPrice = quote
    ? action === "BUY"
      ? quote.bid
      : quote.ask
    : 0;

  useEffect(() => {
    setStopLoss("");
    setTakeProfit("");
    setLotSize("");
    setResult(null);
    setError(null);
  }, [selectedSymbol, action]);

  const handleSubmit = async () => {
    if (!lotSize || !stopLoss || !takeProfit || !entryPrice) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await createTrade({
        symbol: selectedSymbol,
        action,
        entry_price: entryPrice,
        stop_loss: parseFloat(stopLoss),
        take_profit: parseFloat(takeProfit),
        lot_size: parseFloat(lotSize),
      });
      setResult({ id: res.id, status: res.status });
      setShowConfirm(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Trade failed");
    } finally {
      setSubmitting(false);
    }
  };

  const isValid = lotSize && stopLoss && takeProfit && entryPrice > 0;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm">Quick Trade</CardTitle>
          <SignalBadge signal={action} />
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Symbol + Entry */}
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">Symbol</span>
          <span className="font-mono font-medium">{selectedSymbol}</span>
        </div>
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">Entry ({action === "BUY" ? "Bid" : "Ask"})</span>
          <span className="font-mono font-medium">
            {entryPrice > 0 ? formatPrice(entryPrice, selectedSymbol) : "—"}
          </span>
        </div>

        {/* Action Toggle */}
        <div className="grid grid-cols-2 gap-2">
          <Button
            variant={action === "BUY" ? "default" : "outline"}
            size="sm"
            className={action === "BUY" ? "bg-emerald-600 hover:bg-emerald-700" : ""}
            onClick={() => setAction("BUY")}
          >
            BUY
          </Button>
          <Button
            variant={action === "SELL" ? "default" : "outline"}
            size="sm"
            className={action === "SELL" ? "bg-red-600 hover:bg-red-700" : ""}
            onClick={() => setAction("SELL")}
          >
            SELL
          </Button>
        </div>

        {/* Inputs */}
        <div className="space-y-1.5">
          <label className="text-xs text-muted-foreground">Stop Loss</label>
          <Input
            type="number"
            step="any"
            placeholder="0.00000"
            value={stopLoss}
            onChange={(e) => setStopLoss(e.target.value)}
          />
        </div>
        <div className="space-y-1.5">
          <label className="text-xs text-muted-foreground">Take Profit</label>
          <Input
            type="number"
            step="any"
            placeholder="0.00000"
            value={takeProfit}
            onChange={(e) => setTakeProfit(e.target.value)}
          />
        </div>
        <div className="space-y-1.5">
          <label className="text-xs text-muted-foreground">Lot Size</label>
          <Input
            type="number"
            step="any"
            placeholder="0.01"
            value={lotSize}
            onChange={(e) => setLotSize(e.target.value)}
          />
        </div>

        {error && <p className="text-xs text-destructive">{error}</p>}

        {result && (
          <div className="rounded-md border border-emerald-500/30 bg-emerald-500/10 p-2 text-xs">
            Trade submitted — ID: <span className="font-mono">{result.id}</span> ({result.status})
          </div>
        )}

        <Button
          className="w-full"
          disabled={!isValid || submitting}
          onClick={() => setShowConfirm(true)}
        >
          {submitting ? "Submitting..." : action}
        </Button>

        {/* Confirmation Modal */}
        {showConfirm && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
            <Card className="w-[340px] space-y-4">
              <CardHeader>
                <CardTitle className="text-sm">Confirm Trade</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Symbol</span>
                  <span className="font-mono">{selectedSymbol}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Action</span>
                  <SignalBadge signal={action} />
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Entry</span>
                  <span className="font-mono">{formatPrice(entryPrice, selectedSymbol)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Stop Loss</span>
                  <span className="font-mono">{stopLoss}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Take Profit</span>
                  <span className="font-mono">{takeProfit}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Lot Size</span>
                  <span className="font-mono">{lotSize}</span>
                </div>
                <div className="flex gap-2 pt-2">
                  <Button variant="outline" className="flex-1" onClick={() => setShowConfirm(false)}>
                    Cancel
                  </Button>
                  <Button
                    className="flex-1"
                    disabled={submitting}
                    onClick={handleSubmit}
                  >
                    {submitting ? "..." : "Confirm"}
                  </Button>
                </div>
              </CardContent>
            </Card>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
