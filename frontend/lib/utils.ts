import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatNumber(n: number | null | undefined, decimals = 2) {
  if (n == null || isNaN(n)) return "—"
  return n.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
}

export function formatPercent(n: number | null | undefined) {
  if (n == null || isNaN(n)) return "—"
  return `${(n * 100).toFixed(1)}%`
}

export function formatPrice(n: number | null | undefined, symbol: string) {
  if (n == null || isNaN(n)) return "—"
  return symbol.includes("JPY") ? n.toFixed(3) : n.toFixed(5)
}
