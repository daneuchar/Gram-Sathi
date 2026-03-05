"use client";

import { useActiveCalls } from "@/lib/queries";
import { LiveCallCard } from "@/components/live-call-card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Radio } from "lucide-react";

export default function LiveMonitorPage() {
  const { data, isLoading } = useActiveCalls();
  const calls = data?.calls ?? [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Live Calls</h1>
        <Badge variant="secondary" className="text-sm">
          {isLoading ? "..." : calls.length}
        </Badge>
      </div>

      {/* Loading state */}
      {isLoading && (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-[72px] w-full rounded-xl" />
          ))}
        </div>
      )}

      {/* Empty state */}
      {!isLoading && calls.length === 0 && (
        <div className="flex flex-col items-center justify-center py-24 text-muted-foreground">
          <Radio className="mb-3 h-10 w-10 opacity-40" />
          <p className="text-sm">No active calls right now</p>
        </div>
      )}

      {/* Active calls list */}
      {!isLoading && calls.length > 0 && (
        <div className="space-y-3">
          {calls.map((call) => (
            <LiveCallCard key={call.call_sid} call={call} />
          ))}
        </div>
      )}
    </div>
  );
}
