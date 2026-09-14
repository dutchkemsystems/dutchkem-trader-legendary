import sys, json
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from backtest_optimized import *
import pandas as pd
import numpy as np

for sym in ['EURUSD','GBPUSD','USDJPY','XAUUSD','USDCHF','AUDUSD','USDCAD','NZDUSD','EURGBP','EURJPY']:
    df = load_candles(sym)
    if df is None: continue
    df = df.iloc[-2000:]
    cfg = SYMBOL_CONFIG.get(sym, SYMBOL_CONFIG['EURUSD'])
    df_s = generate_signals(df, cfg)
    r = run_backtest(df_s, sym, cfg)
    trades = r['trades']
    if not trades: continue

    print(f'\n{"="*50}')
    print(f'{sym}: {r["total_trades"]} trades, WR={r["win_rate"]}%, P/L=${r["total_pnl"]:+.2f}')
    print(f'{"="*50}')

    for reason in ['SL','TP','REVERSAL','TIME','END']:
        subset = [t for t in trades if t['exit_reason'] == reason]
        if not subset: continue
        wins = [t for t in subset if t['pnl'] > 0]
        losses = [t for t in subset if t['pnl'] <= 0]
        total_pnl = sum(t['pnl'] for t in subset)
        wr = len(wins)/len(subset)*100
        avg_w = np.mean([t['pnl'] for t in wins]) if wins else 0
        avg_l = np.mean([t['pnl'] for t in losses]) if losses else 0
        avg_bars = np.mean([t['bars_held'] for t in subset])
        print(f'  {reason:10s}: {len(subset):3d}t WR={wr:4.0f}% P/L=${total_pnl:+8.2f} avgW=${avg_w:+.2f} avgL=${avg_l:+.2f} bars={avg_bars:.1f}')

    # Key insight: what % of trades hit SL early (<=5 bars)?
    early_sl = [t for t in trades if t['exit_reason'] == 'SL' and t['bars_held'] <= 5]
    late_sl = [t for t in trades if t['exit_reason'] == 'SL' and t['bars_held'] > 5]
    print(f'  SL breakdown: {len(early_sl)} early(<=5bars) WR={len([t for t in early_sl if t["pnl"]>0])/max(1,len(early_sl))*100:.0f}% | {len(late_sl)} late(>5bars) WR={len([t for t in late_sl if t["pnl"]>0])/max(1,len(late_sl))*100:.0f}%')
