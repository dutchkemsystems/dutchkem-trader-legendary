"use client";

import { useSymbolStore } from "@/stores/symbol-store";
import { useAuthStore } from "@/stores/auth-store";
import { useRouter } from "next/navigation";

export function Header() {
  const { selectedSymbol, watchlist, selectSymbol, selectedTimeframe, selectTimeframe } =
    useSymbolStore();
  const logout = useAuthStore((s) => s.logout);
  const router = useRouter();

  function handleLogout() {
    logout();
    router.push("/login");
  }

  return (
    <header className="flex h-14 items-center justify-between border-b border-border bg-card px-4">
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <label htmlFor="symbol-select" className="text-sm font-medium">
            Symbol
          </label>
          <select
            id="symbol-select"
            value={selectedSymbol}
            onChange={(e) => selectSymbol(e.target.value)}
            className="rounded-md border border-input bg-background px-2 py-1 text-sm"
          >
            {watchlist.map((item) => (
              <option key={item.symbol} value={item.symbol}>
                {item.symbol}
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-2">
          <label htmlFor="timeframe-select" className="text-sm font-medium">
            Timeframe
          </label>
          <select
            id="timeframe-select"
            value={selectedTimeframe}
            onChange={(e) => selectTimeframe(e.target.value as "1M" | "5M" | "15M" | "1H" | "4H" | "1D")}
            className="rounded-md border border-input bg-background px-2 py-1 text-sm"
          >
            {(["1M", "5M", "15M", "1H", "4H", "1D"] as const).map((tf) => (
              <option key={tf} value={tf}>
                {tf}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-success" />
          <span className="text-xs text-muted-foreground">Connected</span>
        </div>
        <button
          onClick={handleLogout}
          className="rounded-md px-3 py-1 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
        >
          Logout
        </button>
      </div>
    </header>
  );
}
