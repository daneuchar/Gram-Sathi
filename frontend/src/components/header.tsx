"use client";

import { usePathname } from "next/navigation";
import { getPageTitle } from "@/lib/navigation";
import { useStats } from "@/lib/queries";
import { Badge } from "@/components/ui/badge";
import { Radio } from "lucide-react";

export function Header() {
  const pathname = usePathname();
  const { data: stats } = useStats();

  return (
    <header className="flex h-14 items-center justify-between border-b border-border bg-white px-6">
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-semibold text-foreground">
          {getPageTitle(pathname)}
        </h1>
      </div>

      <div className="flex items-center gap-3">
        {stats && stats.active_calls > 0 && (
          <Badge className="gap-1.5 bg-success/10 text-success hover:bg-success/15 border-0">
            <Radio className="h-3 w-3" />
            {stats.active_calls} Active Call{stats.active_calls !== 1 ? "s" : ""}
          </Badge>
        )}
      </div>
    </header>
  );
}
