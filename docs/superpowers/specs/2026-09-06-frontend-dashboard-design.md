# Dutchkem Trader Frontend Dashboard — Design Spec

**Date:** 2026-09-06
**Status:** Approved
**Sub-Project:** 4 of 8 — Frontend UI

---

## Overview

A Next.js trading dashboard providing Full Market Intelligence — real-time consensus from 12 AI analysts, legendary module outputs, multi-timeframe scanner, and portfolio tracking. Connects to the existing FastAPI backend via REST API and WebSocket.

---

## Goals

1. **Full Market Intelligence** — Display all 12 analyst signals, consensus engine results, legendary module outputs, and multi-timeframe scanner data in a single unified dashboard
2. **Real-time Data** — WebSocket-driven live market prices, REST polling for analyst/consensus/scanner updates
3. **Actionable Decisions** — Quick-trade execution buttons (BUY/SELL/HOLD) directly from the dashboard
4. **Portfolio Visibility** — Track open positions, P&L, and trade history in a dedicated tab
5. **Professional UX** — Dense, dark-mode trading dashboard with color-coded signals and custom SVG visualizations

---

## Non-Goals

- **Mobile app** (Sub-Project 6)
- **Order execution backend** (Sub-Project 2) — frontend sends trade commands but backend execution is separate
- **Broker integration** (Sub-Project 4) — frontend is UI only
- **User registration/multi-user** — single-user with JWT auth only
- **Symbol search/database** — hardcoded watchlist of 10 symbols
- **Advanced charting indicators** — TradingView Lightweight Charts handles this natively
- **Real-time P&L calculation** — backend provides unrealized_pnl, frontend displays it

---

## Tech Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Framework | Next.js 15 (App Router) | Modern React, SSR capable, great DX |
| Language | TypeScript | Type safety, backend type sharing |
| Styling | Tailwind CSS v4 | Utility-first, fast iteration |
| Components | Shadcn/ui (New York) | Beautiful, accessible, customizable |
| State | Zustand | Lightweight, no boilerplate |
| Charts | TradingView Lightweight Charts | Industry standard for trading |
| Visuals | D3.js + raw SVG | Custom analyst/consensus diagrams |
| Data Charts | Recharts | Simple bar/line charts for P&L |
| Auth | JWT (localStorage) | Single-user, simple |
| HTTP | Axios | Interceptors for JWT, error handling |
| WebSocket | Native WebSocket | Real-time market prices |

---

## Project Structure

```
frontend/
├── app/
│   ├── layout.tsx              # Root layout (providers, font, theme)
│   ├── page.tsx                # Redirect → /dashboard
│   ├── login/
│   │   └── page.tsx            # JWT login form
│   └── dashboard/
│       ├── layout.tsx          # Dashboard layout (sidebar + header)
│       ├── page.tsx            # Primary: Full Market Intelligence
│       ├── analysts/
│       │   └── page.tsx        # Deep dive per analyst
│       ├── portfolio/
│       │   └── page.tsx        # Positions, P&L, trade history
│       ├── scanner/
│       │   └── page.tsx        # Full multi-timeframe scanner
│       └── market/
│           └── page.tsx        # Charts and market data
├── components/
│   ├── ui/                     # Shadcn/ui primitives
│   │   ├── button.tsx
│   │   ├── card.tsx
│   │   ├── badge.tsx
│   │   ├── table.tsx
│   │   ├── input.tsx
│   │   ├── skeleton.tsx
│   │   └── tooltip.tsx
│   ├── layout/
│   │   ├── sidebar.tsx         # Left navigation sidebar
│   │   ├── header.tsx          # Symbol selector + status
│   │   └── page-wrapper.tsx    # Page container
│   ├── dashboard/
│   │   ├── consensus-gauge.tsx     # Radial gauge (SVG)
│   │   ├── analyst-grid.tsx        # 12 colored dots grid
│   │   ├── analyst-dot.tsx         # Single analyst indicator
│   │   ├── legendary-modules.tsx   # Seykota/Turtle/Pyramiding
│   │   ├── scanner-heatmap.tsx     # 6-timeframe heatmap
│   │   ├── vote-breakdown.tsx      # Stacked BUY/SELL/HOLD bar
│   │   └── quick-trade.tsx         # Trade execution panel
│   ├── charts/
│   │   ├── price-chart.tsx         # TradingView candlestick
│   │   └── indicators.tsx          # RSI/MACD/BB overlay
│   ├── visuals/
│   │   ├── consensus-gauge-svg.tsx # Custom radial gauge
│   │   ├── heatmap-cell.tsx        # Scanner heatmap cell
│   │   └── signal-badge.tsx        # BUY/SELL/HOLD badge
│   └── portfolio/
│       ├── positions-table.tsx     # Open positions
│       ├── trade-history.tsx       # Past trades
│       └── pnl-chart.tsx           # P&L line chart
├── hooks/
│   ├── use-websocket.ts        # WebSocket connection manager
│   ├── use-market-data.ts      # REST: candles, quotes
│   ├── use-analysts.ts         # REST: analyst signals
│   ├── use-consensus.ts        # REST: consensus result
│   ├── use-scanner.ts          # REST: scanner results
│   ├── use-legendary.ts        # REST: legendary modules
│   ├── use-trades.ts           # REST: trade CRUD
│   ├── use-positions.ts        # REST: position listing
│   └── use-auth.ts             # JWT auth state
├── lib/
│   ├── api.ts                  # Axios instance with JWT interceptor
│   ├── ws.ts                   # WebSocket client wrapper
│   ├── types.ts                # TypeScript types (mirrors backend)
│   ├── constants.ts            # Watchlist, timeframes, colors
│   └── utils.ts                # cn(), formatNumber(), etc.
├── stores/
│   ├── auth-store.ts           # JWT token, login/logout
│   ├── symbol-store.ts         # Selected symbol, watchlist
│   └── market-store.ts         # Live prices, candles
├── styles/
│   └── globals.css             # Tailwind imports + theme vars
├── next.config.ts
├── tailwind.config.ts
├── tsconfig.json
├── package.json
└── .env.local                  # NEXT_PUBLIC_API_URL, NEXT_PUBLIC_WS_URL
```

---

## Data Types (mirrors backend)

```typescript
// Signal types
type Signal = "BUY" | "SELL" | "HOLD";
type TrendSignal = "BULLISH" | "BEARISH" | "NEUTRAL" | "CHOP";

// Analyst result
interface AnalystResult {
  analyst_name: string;
  symbol: string;
  timeframe: string;
  signal: Signal;
  confidence: number; // 0.0 - 1.0
  reasoning: string;
  data: Record<string, unknown>;
  timestamp: string;
}

// Consensus result
interface ConsensusResult {
  action: Signal;
  confidence: number;
  agreement_pct: number;
  reason: string;
  votes: Record<string, Signal>; // analyst_name → signal
}

// Scanner result
interface ScanResult {
  symbol: string;
  h1_bias: string;
  alignment: number;
  overall_signal: Signal;
  overall_confidence: number;
  timeframes: Record<string, TimeframeResult>;
}

interface TimeframeResult {
  timeframe: string;
  signal: Signal;
  confidence: number;
  data: Record<string, unknown>;
}

// Legendary module results
interface SeykotaResult {
  symbol: string;
  trend: TrendSignal;
  confidence: number;
  action: Signal;
  adx: number;
}

interface TurtleSoupResult {
  symbol: string;
  result: {
    signal: Signal;
    confidence: number;
    reason: string;
  } | null;
}

interface PyramidingResult {
  symbol: string;
  entry_count: number;
  max_entries: number;
}

// Market data
interface Candle {
  symbol: string;
  timeframe: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  timestamp: string;
}

interface Tick {
  symbol: string;
  price: number;
  size: number;
  timestamp: string;
  exchange: string;
}

interface Quote {
  symbol: string;
  bid: number;
  ask: number;
  bid_size: number;
  ask_size: number;
  spread: number;
  timestamp: string;
}

// Portfolio
interface Trade {
  id: string;
  symbol: string;
  side: Signal;
  entry_price: number;
  quantity: number;
  status: string;
  created_at: string;
}

interface Position {
  id: string;
  symbol: string;
  quantity: number;
  avg_entry_price: number;
  current_price: number;
  unrealized_pnl: number;
}

// Watchlist
interface WatchlistItem {
  symbol: string;
  name: string;
  category: "forex" | "equity";
}
```

---

## Page Specifications

### 1. Login Page (`/login`)

Simple JWT login form:
- Username + password fields
- "Login" button
- On success: store JWT in localStorage, redirect to `/dashboard`
- On failure: show error message
- No signup, no forgot password

### 2. Primary Dashboard (`/dashboard`)

**Layout:**
```
┌─────────────────────────────────────────────────────────────┐
│  Header: [Symbol Selector ▼] [Last Price] [WS Status]       │
├──────────┬──────────────────────────────────────────────────┤
│          │  ┌──────────────┐  ┌────────────────────────┐   │
│ Sidebar  │  │  CONSENSUS   │  │  PRICE CHART            │   │
│          │  │  (SVG Gauge) │  │  TradingView LW Charts  │   │
│ [Dash]   │  │  BUY 78%     │  │  Candlestick + Volume   │   │
│ [Analyst]│  │  9/12 agree  │  │                         │   │
│ [Portf.] │  └──────────────┘  └────────────────────────┘   │
│ [Scan]   │  ┌──────────────┐  ┌────────────────────────┐   │
│ [Market] │  │  LEGENDARY   │  │  12 ANALYST GRID        │   │
│          │  │  Seykota: ▲  │  │  ●●●●●●                 │   │
│          │  │  Turtle: ▼   │  │  ●●●●●●                 │   │
│          │  │  Pyram: 2/4  │  │  (colored dots)          │   │
│          │  └──────────────┘  └────────────────────────┘   │
│          │  ┌──────────────┐  ┌────────────────────────┐   │
│          │  │ QUICK TRADE  │  │  SCANNER HEATMAP        │   │
│          │  │ [BUY] [SELL] │  │  1M 5M 15M 1H 4H D     │   │
│          │  │ [HOLD]       │  │  ■■ ■■ ■■ ■■ ■■ ■■     │   │
│          │  └──────────────┘  └────────────────────────┘   │
├──────────┴──────────────────────────────────────────────────┤
│  Footer: [12 analysts] [6 providers] [WS: connected]        │
└─────────────────────────────────────────────────────────────┘
```

**Components:**

#### ConsensusGauge (SVG)
- Radial gauge showing agreement % (0-100%)
- Center text: BUY/SELL/HOLD in signal color
- Bottom text: confidence percentage
- Color: BUY=emerald, SELL=red, HOLD=amber

#### AnalystGrid (12 dots)
- 2 rows of 6 colored circles
- Each circle: analyst name abbreviation + confidence %
- Color: emerald=BUY, red=SELL, amber=HOLD
- Hover tooltip: full analyst name + reasoning snippet

#### LegendaryModules
- 3 cards stacked vertically
- Seykota: trend arrow + ADX value
- Turtle Soup: signal or "No setup"
- Pyramiding: entry count / max

#### ScannerHeatmap (6 cells)
- Row of 6 cells (1M, 5M, 15M, 1H, 4H, Daily)
- Cell color intensity = confidence level
- Cell text: BUY/SELL/HOLD
- H1 cell highlighted as bias anchor

#### QuickTrade
- 3 buttons: BUY (green), SELL (red), HOLD (amber)
- Symbol + quantity input
- Confirmation modal before execution

#### PriceChart
- TradingView Lightweight Charts
- Candlestick chart with volume
- Timeframe selector (1M, 5M, 15M, 1H, 4H, 1D)

### 3. Analysts Page (`/dashboard/analysts`)

- Grid of 12 analyst cards
- Each card shows: name, signal, confidence bar, reasoning text
- Click to expand: full reasoning, data breakdown, historical signals
- Filter by signal type (BUY/SELL/HOLD)

### 4. Portfolio Page (`/dashboard/portfolio`)

- **Positions Table**: symbol, quantity, entry price, current price, unrealized P&L, close button
- **Trade History Table**: symbol, side, entry price, quantity, status, date
- **P&L Chart**: line chart of cumulative P&L over time

### 5. Scanner Page (`/dashboard/scanner`)

- Full multi-timeframe scanner view
- 6 timeframes with individual signals and confidence
- Alignment percentage display
- H1 bias indicator
- Comparison view for multiple symbols

### 6. Market Page (`/dashboard/market`)

- Full-screen TradingView chart
- Multiple timeframe selection
- Technical indicators overlay (RSI, MACD, Bollinger Bands)
- Current quote display (bid/ask/spread)

---

## WebSocket Integration

### Connection Management
```typescript
// hooks/use-websocket.ts
- Connects to ws://localhost:8000/ws/market/{symbol}
- Auto-reconnect on disconnect (exponential backoff)
- Heartbeat every 30s
- Exposes: isConnected, lastMessage, subscribe(symbol)
```

### Message Flow
```
WebSocket → useWebSocket() → marketStore → PriceChart updates
                                           → Header price updates
```

### REST Polling
```
useAnalysts()    → poll /api/v1/analysts/{name}/analyze?symbol=X  → every 5s
useConsensus()   → poll /api/v1/consensus/{symbol}                → every 5s
useScanner()     → poll /api/v1/scanner/{symbol}                  → every 10s
useLegendary()   → on-demand (user clicks refresh)                → manual
useTrades()      → poll /api/v1/trades                            → every 30s
usePositions()   → poll /api/v1/positions                         → every 30s
```

---

## State Management (Zustand)

### auth-store
```typescript
{
  token: string | null;
  isAuthenticated: boolean;
  login(username, password): Promise<void>;
  logout(): void;
}
```

### symbol-store
```typescript
{
  selectedSymbol: string;           // default: "EURUSD"
  watchlist: WatchlistItem[];       // 10 symbols
  selectSymbol(symbol): void;
}
```

### market-store
```typescript
{
  livePrice: Record<string, number>;  // symbol → price
  candles: Candle[];
  quote: Quote | null;
  updatePrice(symbol, price): void;
  setCandles(candles): void;
}
```

---

## Color System

| Signal | Color | Tailwind Class |
|--------|-------|----------------|
| BUY | Emerald | `bg-emerald-500`, `text-emerald-500` |
| SELL | Red | `bg-red-500`, `text-red-500` |
| HOLD | Amber | `bg-amber-500`, `text-amber-500` |
| BULLISH | Emerald | `text-emerald-400` |
| BEARISH | Red | `text-red-400` |
| NEUTRAL | Gray | `text-gray-400` |
| CHOP | Gray | `text-gray-500` |

---

## Environment Variables

```env
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
NEXT_PUBLIC_WS_URL=ws://localhost:8000/ws
```

---

## Authentication Flow

1. User visits `/dashboard` → redirect to `/login` if no JWT
2. User submits credentials → POST `/api/v1/auth/login` (backend endpoint)
3. On success: store JWT in localStorage, redirect to `/dashboard`
4. All API requests include `Authorization: Bearer {token}` header
5. Axios interceptor handles 401 → redirect to `/login`
6. WebSocket connects with token as query param: `?token={jwt}`

---

## Dependencies

```json
{
  "next": "^15.0.0",
  "react": "^19.0.0",
  "react-dom": "^19.0.0",
  "zustand": "^5.0.0",
  "axios": "^1.7.0",
  "lightweight-charts": "^4.2.0",
  "recharts": "^2.12.0",
  "d3": "^7.9.0",
  "clsx": "^2.1.0",
  "tailwind-merge": "^2.2.0",
  "class-variance-authority": "^0.7.0",
  "lucide-react": "^0.400.0",
  "@radix-ui/react-slot": "^1.1.0",
  "@radix-ui/react-tooltip": "^1.1.0"
}
```

---

## Implementation Order

| Phase | What | Depends On |
|-------|------|------------|
| 1 | Project scaffold + Shadcn/ui setup | None |
| 2 | Auth (login page + JWT store) | Phase 1 |
| 3 | Layout (sidebar + header + routing) | Phase 2 |
| 4 | Types + API client + hooks | Phase 3 |
| 5 | WebSocket integration | Phase 4 |
| 6 | Primary Dashboard (consensus, analysts, scanner) | Phase 5 |
| 7 | Price chart (TradingView) | Phase 5 |
| 8 | Custom SVG visuals | Phase 6 |
| 9 | Analysts deep-dive page | Phase 6 |
| 10 | Portfolio page | Phase 6 |
| 11 | Scanner page | Phase 6 |
| 12 | Market page | Phase 7 |
| 13 | Quick trade execution | Phase 6 |

---

## Verification

1. `npm run build` — zero errors
2. `npm run dev` — dashboard loads at localhost:3000
3. Login page renders, JWT auth works
4. WebSocket connects and shows live prices
5. All 12 analyst dots render with correct colors
6. Consensus gauge shows real data from backend
7. Scanner heatmap renders 6 timeframes
8. Navigation between all tabs works
9. Portfolio shows positions and trade history
10. Dark mode looks professional and readable
