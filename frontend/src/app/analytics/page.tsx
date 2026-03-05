"use client";

import { BarChart3, Globe, UserPlus, Users } from "lucide-react";
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

import { useAnalytics, useStats } from "@/lib/queries";
import { formatShortDate } from "@/lib/format";
import { downloadCSV } from "@/lib/export";
import { StatCard } from "@/components/stat-card";
import { SectionCard } from "@/components/section-card";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";

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

export default function AnalyticsPage() {
  const { data: analytics, isLoading: analyticsLoading } = useAnalytics();
  const { data: stats, isLoading: statsLoading } = useStats();

  function handleExportCSV() {
    if (!analytics) return;
    const rows = [
      ...analytics.call_volume_30d.map((d) => ({
        type: "call_volume",
        date: d.date,
        value: d.calls,
      })),
      ...analytics.language_distribution.map((d) => ({
        type: "language",
        date: d.language,
        value: d.count,
      })),
      ...analytics.tool_usage.map((d) => ({
        type: "tool_usage",
        date: d.tool,
        value: d.count,
      })),
    ];
    downloadCSV(rows, "gramvaani-analytics.csv");
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold tracking-tight">Analytics</h1>

      {/* ── Stat Cards ── */}
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
        {analyticsLoading || statsLoading ? (
          <>
            <StatCardSkeleton />
            <StatCardSkeleton />
            <StatCardSkeleton />
            <StatCardSkeleton />
          </>
        ) : (
          <>
            <StatCard
              title="Total Calls This Month"
              value={analytics?.total_calls_month ?? 0}
              icon={BarChart3}
              color="bg-blue-100 text-blue-600"
            />
            <StatCard
              title="Languages Active"
              value={analytics?.languages_active ?? 0}
              icon={Globe}
              color="bg-purple-100 text-purple-600"
            />
            <StatCard
              title="New Farmers"
              value={analytics?.new_farmers_month ?? 0}
              icon={UserPlus}
              color="bg-green-100 text-green-600"
            />
            <StatCard
              title="Total Farmers"
              value={stats?.total_farmers ?? 0}
              icon={Users}
              color="bg-orange-100 text-orange-600"
            />
          </>
        )}
      </div>

      {/* ── Charts — 2-column grid ── */}
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

        {/* Call Volume (30 Days) */}
        <SectionCard title="Call Volume (30 Days)">
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

        {/* Tool Usage */}
        <SectionCard title="Tool Usage">
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
      </div>

      {/* ── Bottom Section — 2-column grid ── */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Top States */}
        <SectionCard title="Top States">
          {analyticsLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-5 w-40" />
              ))}
            </div>
          ) : (
            <ol className="space-y-1.5 text-sm">
              {(analytics?.top_states ?? []).map((s, i) => (
                <li key={s} className="flex items-center gap-2">
                  <span className="flex h-5 w-5 items-center justify-center rounded-full bg-muted text-xs font-medium">
                    {i + 1}
                  </span>
                  <span>{s}</span>
                </li>
              ))}
              {(analytics?.top_states ?? []).length === 0 && (
                <li className="text-muted-foreground">No data yet</li>
              )}
            </ol>
          )}
        </SectionCard>

        {/* Export */}
        <SectionCard title="Export Data">
          <div className="flex flex-col items-start gap-3">
            <p className="text-sm text-muted-foreground">
              Download analytics data as a CSV file for offline analysis.
            </p>
            <Button onClick={handleExportCSV} disabled={analyticsLoading}>
              Export Analytics CSV
            </Button>
          </div>
        </SectionCard>
      </div>
    </div>
  );
}
