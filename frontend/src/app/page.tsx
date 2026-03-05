"use client";

import { Radio, PhoneCall, Users, Clock } from "lucide-react";
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

import { useStats, useAnalytics } from "@/lib/queries";
import { formatDuration, formatShortDate } from "@/lib/format";
import { StatCard } from "@/components/stat-card";
import { SectionCard } from "@/components/section-card";
import { Skeleton } from "@/components/ui/skeleton";

function shortDateLabel(label: unknown): string {
  return formatShortDate(String(label));
}

function StatCardSkeleton() {
  return (
    <div className="flex items-center gap-4 rounded-xl border bg-card p-5 shadow-sm">
      <Skeleton className="h-10 w-10 rounded-lg" />
      <div className="space-y-2">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-7 w-16" />
      </div>
    </div>
  );
}

function ChartSkeleton() {
  return <Skeleton className="h-[220px] w-full rounded-md" />;
}

export default function OverviewPage() {
  const { data: stats, isLoading: statsLoading } = useStats();
  const { data: analytics, isLoading: analyticsLoading } = useAnalytics();

  return (
    <div className="space-y-6">
      {/* Stat Cards */}
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
        {statsLoading ? (
          <>
            <StatCardSkeleton />
            <StatCardSkeleton />
            <StatCardSkeleton />
            <StatCardSkeleton />
          </>
        ) : (
          <>
            <StatCard
              title="Active Calls"
              value={stats?.active_calls ?? 0}
              icon={Radio}
              color="bg-blue-100 text-blue-600"
            />
            <StatCard
              title="Calls Today"
              value={stats?.calls_today ?? 0}
              icon={PhoneCall}
              color="bg-green-100 text-green-600"
            />
            <StatCard
              title="Farmers Served"
              value={stats?.total_farmers ?? 0}
              icon={Users}
              color="bg-purple-100 text-purple-600"
            />
            <StatCard
              title="Avg Duration"
              value={formatDuration(stats?.avg_duration_seconds ?? null)}
              icon={Clock}
              color="bg-orange-100 text-orange-600"
            />
          </>
        )}
      </div>

      {/* Charts — 2-column grid */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Call Volume (7 Days) */}
        <SectionCard title="Call Volume (7 Days)">
          {analyticsLoading ? (
            <ChartSkeleton />
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={analytics?.call_volume_7d ?? []}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis
                  dataKey="date"
                  tickFormatter={shortDateLabel}
                  fontSize={12}
                  tickLine={false}
                  axisLine={false}
                />
                <YAxis
                  fontSize={12}
                  tickLine={false}
                  axisLine={false}
                  allowDecimals={false}
                />
                <Tooltip
                  labelFormatter={shortDateLabel}
                  contentStyle={{
                    borderRadius: "8px",
                    border: "1px solid #E2E8F0",
                    fontSize: "13px",
                  }}
                />
                <Bar
                  dataKey="calls"
                  fill="#3B82F6"
                  radius={[4, 4, 0, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          )}
        </SectionCard>

        {/* Query Type Breakdown */}
        <SectionCard title="Query Type Breakdown">
          {analyticsLoading ? (
            <ChartSkeleton />
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={analytics?.tool_usage ?? []}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis
                  dataKey="tool"
                  fontSize={12}
                  tickLine={false}
                  axisLine={false}
                />
                <YAxis
                  fontSize={12}
                  tickLine={false}
                  axisLine={false}
                  allowDecimals={false}
                />
                <Tooltip
                  contentStyle={{
                    borderRadius: "8px",
                    border: "1px solid #E2E8F0",
                    fontSize: "13px",
                  }}
                />
                <Bar
                  dataKey="count"
                  fill="#16A34A"
                  radius={[4, 4, 0, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          )}
        </SectionCard>

        {/* Daily Volume (30 Days) */}
        <SectionCard title="Daily Volume (30 Days)">
          {analyticsLoading ? (
            <ChartSkeleton />
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={analytics?.call_volume_30d ?? []}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis
                  dataKey="date"
                  tickFormatter={shortDateLabel}
                  fontSize={12}
                  tickLine={false}
                  axisLine={false}
                />
                <YAxis
                  fontSize={12}
                  tickLine={false}
                  axisLine={false}
                  allowDecimals={false}
                />
                <Tooltip
                  labelFormatter={shortDateLabel}
                  contentStyle={{
                    borderRadius: "8px",
                    border: "1px solid #E2E8F0",
                    fontSize: "13px",
                  }}
                />
                <Line
                  type="monotone"
                  dataKey="calls"
                  stroke="#3B82F6"
                  strokeWidth={2}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          )}
        </SectionCard>

        {/* Language Distribution */}
        <SectionCard title="Language Distribution">
          {analyticsLoading ? (
            <ChartSkeleton />
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={analytics?.language_distribution ?? []}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis
                  dataKey="language"
                  fontSize={12}
                  tickLine={false}
                  axisLine={false}
                />
                <YAxis
                  fontSize={12}
                  tickLine={false}
                  axisLine={false}
                  allowDecimals={false}
                />
                <Tooltip
                  contentStyle={{
                    borderRadius: "8px",
                    border: "1px solid #E2E8F0",
                    fontSize: "13px",
                  }}
                />
                <Bar
                  dataKey="count"
                  fill="#7C3AED"
                  radius={[4, 4, 0, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          )}
        </SectionCard>
      </div>

      {/* Alerts */}
      <SectionCard title="Alerts">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <span className="inline-block h-2 w-2 rounded-full bg-green-500" />
          No active alerts
        </div>
      </SectionCard>
    </div>
  );
}
