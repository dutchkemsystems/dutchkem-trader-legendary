"use client";

import { useAnalysts } from "@/hooks/use-analysts";
import { AnalystDot } from "./analyst-dot";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export function AnalystGrid() {
  const { resultsArray, loading, error } = useAnalysts();

  if (loading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Analyst Grid</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex gap-2 justify-center">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-8 w-8 rounded-full" />
            ))}
          </div>
          <div className="flex gap-2 justify-center">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-8 w-8 rounded-full" />
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Analyst Grid</CardTitle>
        </CardHeader>
        <CardContent className="flex items-center justify-center h-[100px]">
          <p className="text-sm text-destructive">{error}</p>
        </CardContent>
      </Card>
    );
  }

  if (resultsArray.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Analyst Grid</CardTitle>
        </CardHeader>
        <CardContent className="flex items-center justify-center h-[100px]">
          <p className="text-sm text-muted-foreground">No analyst data</p>
        </CardContent>
      </Card>
    );
  }

  const row1 = resultsArray.slice(0, 6);
  const row2 = resultsArray.slice(6, 12);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Analyst Grid</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <div className="flex gap-2 justify-center">
          {row1.map((analyst) => (
            <AnalystDot key={analyst.analyst_name} analyst={analyst} />
          ))}
        </div>
        <div className="flex gap-2 justify-center">
          {row2.map((analyst) => (
            <AnalystDot key={analyst.analyst_name} analyst={analyst} />
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
