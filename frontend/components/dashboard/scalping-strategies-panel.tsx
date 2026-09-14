'use client';

import { useState, useEffect } from 'react';

interface ScalpingStrategy {
  name: string;
  enabled: boolean;
  trades: number;
  winRate: number;
  pnl: number;
  status: string;
}

interface ScalpTrade {
  ticket: number;
  symbol: string;
  direction: string;
  strategy: string;
  entry: number;
  pnl: number;
  status: string;
}

export function ScalpingStrategiesPanel() {
  const [strategies, setStrategies] = useState<ScalpingStrategy[]>([]);
  const [activeTrades, setActiveTrades] = useState<ScalpTrade[]>([]);
  const [totalPnl, setTotalPnl] = useState(0);
  const [activeTab, setActiveTab] = useState('strategies');

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const res = await fetch('/api/v1/scalping/status');
        const data = await res.json();
        setStrategies(data.strategies);
        setActiveTrades(data.active_trades);
        setTotalPnl(data.total_pnl);
      } catch (err) {
        console.error('Failed to fetch scalping status:', err);
      }
    };
    
    fetchStatus();
    const interval = setInterval(fetchStatus, 5000);
    return () => clearInterval(interval);
  }, []);

  const toggleStrategy = async (name: string, enabled: boolean) => {
    try {
      await fetch(`/api/v1/scalping/toggle/${name}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled }),
      });
      setStrategies(prev => prev.map(s => 
        s.name === name ? { ...s, enabled, status: enabled ? 'active' : 'disabled' } : s
      ));
    } catch (err) {
      console.error('Failed to toggle strategy:', err);
    }
  };

  return (
    <div className="border rounded-lg p-4 bg-card">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold">Scalping Strategies</h2>
        <span className={`text-sm font-medium ${totalPnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>
          Total P&L: ${totalPnl.toFixed(2)}
        </span>
      </div>

      <div className="flex gap-2 mb-4">
        <button
          onClick={() => setActiveTab('strategies')}
          className={`px-3 py-1 text-sm rounded ${activeTab === 'strategies' ? 'bg-primary text-primary-foreground' : 'bg-secondary'}`}
        >
          Strategies
        </button>
        <button
          onClick={() => setActiveTab('trades')}
          className={`px-3 py-1 text-sm rounded ${activeTab === 'trades' ? 'bg-primary text-primary-foreground' : 'bg-secondary'}`}
        >
          Active Trades
        </button>
        <button
          onClick={() => setActiveTab('performance')}
          className={`px-3 py-1 text-sm rounded ${activeTab === 'performance' ? 'bg-primary text-primary-foreground' : 'bg-secondary'}`}
        >
          Performance
        </button>
      </div>

      {activeTab === 'strategies' && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          {strategies.map((s) => (
            <div key={s.name} className="border rounded p-3">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium truncate">{s.name}</span>
                <button
                  onClick={() => toggleStrategy(s.name, !s.enabled)}
                  className={`w-10 h-5 rounded-full transition-colors ${s.enabled ? 'bg-green-500' : 'bg-gray-300'}`}
                >
                  <div className={`w-4 h-4 rounded-full bg-white transition-transform ${s.enabled ? 'translate-x-5' : 'translate-x-0.5'}`} />
                </button>
              </div>
              <div className="text-xs text-muted-foreground space-y-1">
                <div>Trades: {s.trades}</div>
                <div>Win Rate: {s.winRate}%</div>
                <div className={s.pnl >= 0 ? 'text-green-500' : 'text-red-500'}>
                  P&L: ${s.pnl.toFixed(2)}
                </div>
              </div>
              <div className={`mt-2 text-xs px-2 py-0.5 rounded ${s.status === 'active' ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-600'}`}>
                {s.status}
              </div>
            </div>
          ))}
        </div>
      )}

      {activeTab === 'trades' && (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b">
              <th className="text-left p-2">Ticket</th>
              <th className="text-left p-2">Symbol</th>
              <th className="text-left p-2">Direction</th>
              <th className="text-left p-2">Strategy</th>
              <th className="text-left p-2">Entry</th>
              <th className="text-left p-2">P&L</th>
            </tr>
          </thead>
          <tbody>
            {activeTrades.length === 0 ? (
              <tr><td colSpan={6} className="p-4 text-center text-muted-foreground">No active trades</td></tr>
            ) : (
              activeTrades.map((t) => (
                <tr key={t.ticket} className="border-b">
                  <td className="p-2">{t.ticket}</td>
                  <td className="p-2">{t.symbol}</td>
                  <td className="p-2">
                    <span className={`px-2 py-0.5 rounded text-xs ${t.direction === 'BUY' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
                      {t.direction}
                    </span>
                  </td>
                  <td className="p-2">{t.strategy}</td>
                  <td className="p-2">{t.entry}</td>
                  <td className={`p-2 ${t.pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                    ${t.pnl.toFixed(2)}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      )}

      {activeTab === 'performance' && (
        <div className="grid grid-cols-2 gap-4">
          <div className="border rounded p-4">
            <h3 className="text-sm font-medium mb-2">Per-Strategy Performance</h3>
            {strategies.map((s) => (
              <div key={s.name} className="flex justify-between text-xs mb-1">
                <span className="truncate">{s.name}</span>
                <span className={s.pnl >= 0 ? 'text-green-500' : 'text-red-500'}>
                  {s.winRate}% WR | ${s.pnl.toFixed(2)}
                </span>
              </div>
            ))}
          </div>
          <div className="border rounded p-4">
            <h3 className="text-sm font-medium mb-2">Cumulative Scalp P&L</h3>
            <div className="h-32 flex items-center justify-center text-muted-foreground text-sm">
              P&L Chart (to be implemented)
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
