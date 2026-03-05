"use client";

import { useHealth } from "@/lib/queries";
import { SectionCard } from "@/components/section-card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { RefreshCw } from "lucide-react";

const SERVICES = [
  { name: "FastAPI Backend", key: "backend" },
  { name: "PostgreSQL", key: "postgres" },
  { name: "LiveKit Server", key: "livekit" },
  { name: "Sarvam TTS", key: "sarvam_tts" },
  { name: "Bedrock LLM", key: "bedrock_llm" },
];

function statusDot(status: string) {
  switch (status) {
    case "healthy":
      return "bg-success";
    case "degraded":
      return "bg-warning";
    case "down":
      return "bg-danger";
    default:
      return "bg-muted-foreground";
  }
}

function statusBadge(status: string) {
  switch (status) {
    case "healthy":
      return "text-success border-success/30 bg-success/10";
    case "degraded":
      return "text-warning border-warning/30 bg-warning/10";
    case "down":
      return "text-danger border-danger/30 bg-danger/10";
    default:
      return "";
  }
}

export default function SystemHealthPage() {
  const { data, isLoading, dataUpdatedAt } = useHealth();

  const isApiUp = data?.status === "ok";

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">
          System Health
        </h1>
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <RefreshCw className="h-3.5 w-3.5" />
          {dataUpdatedAt
            ? `Last updated: ${new Date(dataUpdatedAt).toLocaleTimeString()}`
            : "Refreshing..."}
        </div>
      </div>

      {/* ── Services Table ── */}
      <div className="rounded-xl border bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Service</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Latency</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading &&
              Array.from({ length: 5 }).map((_, i) => (
                <TableRow key={i}>
                  <TableCell>
                    <Skeleton className="h-4 w-32" />
                  </TableCell>
                  <TableCell>
                    <Skeleton className="h-4 w-16" />
                  </TableCell>
                  <TableCell>
                    <Skeleton className="h-4 w-12" />
                  </TableCell>
                </TableRow>
              ))}

            {!isLoading &&
              SERVICES.map((svc) => {
                const svcStatus =
                  svc.key === "backend" && isApiUp
                    ? "healthy"
                    : isApiUp
                      ? "healthy"
                      : "down";

                return (
                  <TableRow key={svc.key}>
                    <TableCell>
                      <div className="flex items-center gap-2.5">
                        <span
                          className={`inline-block h-2 w-2 rounded-full ${statusDot(svcStatus)}`}
                        />
                        <span className="font-medium">{svc.name}</span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant="outline"
                        className={statusBadge(svcStatus)}
                      >
                        {svcStatus}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-muted-foreground">—</TableCell>
                  </TableRow>
                );
              })}
          </TableBody>
        </Table>
      </div>

      {/* ── Bottom Panels ── */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <SectionCard title="Response Latency">
          <p className="text-sm text-muted-foreground">
            Latency monitoring coming soon
          </p>
        </SectionCard>

        <SectionCard title="Error Counts">
          <div className="space-y-3">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">4xx Errors</span>
              <span className="font-medium">0</span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">5xx Errors</span>
              <span className="font-medium">0</span>
            </div>
          </div>
        </SectionCard>

        <SectionCard title="Cache Hit Rate">
          <div className="space-y-3">
            <div className="space-y-1.5">
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">Weather</span>
                <span className="font-medium">—</span>
              </div>
              <Progress value={0} />
            </div>
            <div className="space-y-1.5">
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">Mandi Prices</span>
                <span className="font-medium">—</span>
              </div>
              <Progress value={0} />
            </div>
          </div>
        </SectionCard>
      </div>
    </div>
  );
}
