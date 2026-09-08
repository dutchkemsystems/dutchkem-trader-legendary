"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { MemorySituation } from "@/lib/types-v5";

export function MemoryContextCard({
  situations,
}: {
  situations: MemorySituation[] | undefined;
}) {
  if (!situations || situations.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Memory Context</CardTitle>
        </CardHeader>
        <CardContent className="flex items-center justify-center h-[120px]">
          <p className="text-sm text-muted-foreground">
            No similar past situations found
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm">Memory Context</CardTitle>
          <Badge variant="default">{situations.length} similar</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {situations.slice(0, 3).map((situation, idx) => (
          <div
            key={idx}
            className="rounded-md border border-border p-2 space-y-1"
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium">{situation.symbol}</span>
              <span className="text-[10px] text-muted-foreground font-mono">
                {Math.round(situation.relevance_score * 100)}% match
              </span>
            </div>
            <p className="text-xs text-muted-foreground line-clamp-2">
              {situation.situation}
            </p>
            {situation.lesson && (
              <p className="text-[10px] text-emerald-400 italic line-clamp-2">
                Lesson: {situation.lesson}
              </p>
            )}
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
