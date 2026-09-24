'use client';

import { useState, useEffect } from 'react';
import { getGoldHedgeStatus, toggleGoldHedge } from '@/lib/api';

interface GoldHedgeStatus {
  active: boolean;
  symbol: string;
  levels: number;
  max_levels?: number;
  total_lots: number;
  directions?: string[];
  peak_profit?: number;
  is_frozen?: boolean;
  created_at?: string;
  enabled?: boolean;
  pnl?: number;
  config?: {
    basket_tp_usd: number;
    freeze_loss_usd: number;
    trailing_tp_enabled: boolean;
  };
}

export function GoldHedgePanel() {
  const [status, setStatus] = useState<GoldHedgeStatus>({
    active: false,
    symbol: 'XAUUSD',
    levels: 0,
    total_lots: 0,
    pnl: 0,
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const data = await getGoldHedgeStatus();
        setStatus(data);
      } catch (err) {
        console.error('Failed to fetch Gold Hedge status:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchStatus();
    const interval = setInterval(fetchStatus, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleToggleGoldHedge = async (enabled: boolean) => {
    try {
      await toggleGoldHedge(enabled);
      setStatus(prev => ({ ...prev, enabled }));
    } catch (err) {
      console.error('Failed to toggle Gold Hedge EA:', err);
    }
  };

  if (loading) {
    return (
      <div className="border rounded-lg p-4 bg-card">
        <h2 className="text-lg font-semibold mb-2">Gold Hedge EA</h2>
        <div className="text-muted-foreground">Loading...</div>
      </div>
    );
  }

  return (
    <div className="border rounded-lg p-4 bg-card">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold">Gold Hedge EA</h2>
        <div className="flex items-center gap-3">
          <span className={`text-sm font-medium ${status.active ? 'text-green-500' : 'text-muted-foreground'}`}>
            {status.active ? 'ACTIVE' : 'INACTIVE'}
          </span>
          <button
            onClick={() => handleToggleGoldHedge(!status.enabled)}
            className={`px-3 py-1 text-sm rounded ${
              status.enabled 
                ? 'bg-green-500/20 text-green-500 hover:bg-green-500/30' 
                : 'bg-secondary hover:bg-secondary/80'
            }`}
          >
            {status.enabled ? 'Enabled' : 'Enable'}
          </button>
        </div>
      </div>

      {/* Basket Overview */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        <div className="border rounded p-3">
          <div className="text-xs text-muted-foreground mb-1">Symbol</div>
          <div className="text-lg font-bold">{status.symbol}</div>
        </div>
        <div className="border rounded p-3">
          <div className="text-xs text-muted-foreground mb-1">Hedge Levels</div>
          <div className="text-lg font-bold">
            {status.levels}
            {status.max_levels && (
              <span className="text-sm text-muted-foreground">/{status.max_levels}</span>
            )}
          </div>
        </div>
        <div className="border rounded p-3">
          <div className="text-xs text-muted-foreground mb-1">Total Lots</div>
          <div className="text-lg font-bold">{status.total_lots.toFixed(2)}</div>
        </div>
        <div className="border rounded p-3">
          <div className="text-xs text-muted-foreground mb-1">P&L</div>
          <div className={`text-lg font-bold ${(status.pnl || 0) >= 0 ? 'text-green-500' : 'text-red-500'}`}>
            ${(status.pnl || 0).toFixed(2)}
          </div>
        </div>
      </div>

      {/* Active Basket Details */}
      {status.active && (
        <div className="border rounded p-3 mb-4">
          <div className="text-sm font-medium mb-2">Active Basket</div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <div className="text-xs text-muted-foreground mb-1">Directions</div>
              <div className="flex gap-1">
                {status.directions?.map((dir, i) => (
                  <span
                    key={i}
                    className={`px-2 py-0.5 text-xs rounded ${
                      dir === 'BUY' ? 'bg-green-500/20 text-green-500' : 'bg-red-500/20 text-red-500'
                    }`}
                  >
                    {dir}
                  </span>
                ))}
              </div>
            </div>
            <div>
              <div className="text-xs text-muted-foreground mb-1">Peak Profit</div>
              <div className="text-sm font-medium">
                ${(status.peak_profit || 0).toFixed(2)}
              </div>
            </div>
            <div>
              <div className="text-xs text-muted-foreground mb-1">Status</div>
              <div className={`text-sm font-medium ${status.is_frozen ? 'text-red-500' : 'text-green-500'}`}>
                {status.is_frozen ? 'FROZEN' : 'NORMAL'}
              </div>
            </div>
            <div>
              <div className="text-xs text-muted-foreground mb-1">Created</div>
              <div className="text-sm font-medium">
                {status.created_at ? new Date(status.created_at).toLocaleTimeString() : '-'}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Configuration */}
      {status.config && (
        <div className="border rounded p-3">
          <div className="text-sm font-medium mb-2">Configuration</div>
          <div className="grid grid-cols-3 gap-4 text-sm">
            <div>
              <div className="text-xs text-muted-foreground">Basket TP</div>
              <div className="font-medium">${status.config.basket_tp_usd}</div>
            </div>
            <div>
              <div className="text-xs text-muted-foreground">Freeze Loss</div>
              <div className="font-medium">${status.config.freeze_loss_usd}</div>
            </div>
            <div>
              <div className="text-xs text-muted-foreground">Trailing TP</div>
              <div className={`font-medium ${status.config.trailing_tp_enabled ? 'text-green-500' : 'text-muted-foreground'}`}>
                {status.config.trailing_tp_enabled ? 'ON' : 'OFF'}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Inactive State */}
      {!status.active && !status.enabled && (
        <div className="text-center py-4 text-muted-foreground text-sm">
          Gold Hedge EA is disabled. Enable it to start automated hedging on XAUUSD.
        </div>
      )}
    </div>
  );
}
