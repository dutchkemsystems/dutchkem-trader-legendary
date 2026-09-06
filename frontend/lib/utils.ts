import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatNumber(n: number, decimals = 2) {
  return n.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
}

export function formatPercent(n: number) {
  return `${(n * 100).toFixed(1)}%`
}

export function formatPrice(n: number, symbol: string) {
  return symbol.includes("JPY") ? n.toFixed(3) : n.toFixed(5)
}
