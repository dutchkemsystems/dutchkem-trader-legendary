"use client";

import { useEffect, useState } from "react";

export function Providers({ children }: { children: React.ReactNode }) {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-zinc-950">
        <div className="flex flex-col items-center gap-4">
          <div className="h-10 w-10 animate-spin rounded-full border-2 border-emerald-400 border-t-transparent" />
          <p className="text-sm text-zinc-400">Loading Dutchkem Trader...</p>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
