"use client";

import { Card, CardContent } from "@/components/ui/card";
import type { LucideIcon } from "lucide-react";

interface StatCardProps {
  title: string;
  value: string | number;
  icon: LucideIcon;
  trend?: string;
  color?: string;
}

export function StatCard({
  title,
  value,
  icon: Icon,
  trend,
  color = "bg-brand/10 text-brand",
}: StatCardProps) {
  return (
    <Card>
      <CardContent className="flex items-center gap-4 p-5">
        <div
          className={`flex h-10 w-10 items-center justify-center rounded-lg ${color}`}
        >
          <Icon className="h-5 w-5" />
        </div>
        <div>
          <p className="text-sm text-muted-foreground">{title}</p>
          <p className="text-2xl font-bold">{value}</p>
          {trend && (
            <p className="text-xs text-muted-foreground">{trend}</p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
