"use client";

import { useState, useEffect, useRef } from "react";
import { useCalls, useTranscript, useTranslate } from "@/lib/queries";
import { formatDate, formatDuration } from "@/lib/format";
import type { Call } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Languages } from "lucide-react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";

const LANGUAGES = ["All", "Hindi", "English", "Marathi", "Telugu", "Tamil"];
const STATUSES = ["All", "completed", "in-progress", "failed"];
const PER_PAGE = 20;

function statusColor(status: string) {
  switch (status) {
    case "completed":
      return "text-success border-success/30 bg-success/10";
    case "in-progress":
      return "text-blue-600 border-blue-300/30 bg-blue-50";
    case "failed":
      return "text-danger border-danger/30 bg-danger/10";
    default:
      return "";
  }
}

export default function CallHistoryPage() {
  // Filter form state
  const [phone, setPhone] = useState("");
  const [language, setLanguage] = useState("All");
  const [status, setStatus] = useState("All");

  // Applied query params (only updated on Apply click)
  const [queryParams, setQueryParams] = useState<{
    page: number;
    per_page: number;
    phone?: string;
    language?: string;
    status?: string;
  }>({ page: 1, per_page: PER_PAGE });

  // Transcript drawer state
  const [selectedCall, setSelectedCall] = useState<Call | null>(null);
  const isLive = selectedCall?.status === "in-progress";
  const { data: transcriptData, isLoading: transcriptLoading } = useTranscript(
    selectedCall?.call_sid ?? null,
    isLive
  );
  const chatEndRef = useRef<HTMLDivElement>(null);

  // Translation state
  const [showTranslation, setShowTranslation] = useState(false);
  const [translations, setTranslations] = useState<Record<number, string>>({});
  const translate = useTranslate();

  // Reset translation state when selecting a different call
  useEffect(() => {
    setShowTranslation(false);
    setTranslations({});
  }, [selectedCall?.call_sid]);

  // Auto-scroll to bottom when new turns arrive during live calls
  useEffect(() => {
    if (isLive && chatEndRef.current) {
      chatEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [isLive, transcriptData?.turns.length]);

  const isEnglish = selectedCall?.language_detected === "en-IN";

  function handleTranslate() {
    if (showTranslation) {
      // Toggle off — just hide translations
      setShowTranslation(false);
      return;
    }

    // If already fetched, just toggle on
    if (Object.keys(translations).length > 0) {
      setShowTranslation(true);
      return;
    }

    // Fetch translations
    const turns = transcriptData?.turns ?? [];
    const textsToTranslate = turns
      .filter((t) => !t.tool_called && t.transcript)
      .map((t) => t.transcript);

    if (textsToTranslate.length === 0) return;

    translate.mutate(
      {
        texts: textsToTranslate,
        source_language: selectedCall?.language_detected ?? "hi-IN",
      },
      {
        onSuccess: (data) => {
          const map: Record<number, string> = {};
          let idx = 0;
          for (const turn of turns) {
            if (!turn.tool_called && turn.transcript) {
              map[turn.turn_number] = data.translations[idx];
              idx++;
            }
          }
          setTranslations(map);
          setShowTranslation(true);
        },
      }
    );
  }

  const { data, isLoading } = useCalls(queryParams);
  const calls = data?.calls ?? [];
  const total = data?.total ?? 0;
  const currentPage = data?.page ?? 1;
  const totalPages = Math.max(1, Math.ceil(total / PER_PAGE));

  function applyFilters() {
    setQueryParams({
      page: 1,
      per_page: PER_PAGE,
      ...(phone ? { phone } : {}),
      ...(language !== "All" ? { language } : {}),
      ...(status !== "All" ? { status } : {}),
    });
  }

  function goToPage(page: number) {
    setQueryParams((prev) => ({ ...prev, page }));
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold tracking-tight">Call History</h1>

      {/* ── Filter Row ── */}
      <div className="flex flex-wrap items-end gap-3">
        <div className="w-48">
          <Input
            placeholder="Search by phone"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
          />
        </div>

        <Select value={language} onValueChange={setLanguage}>
          <SelectTrigger className="w-36">
            <SelectValue placeholder="Language" />
          </SelectTrigger>
          <SelectContent>
            {LANGUAGES.map((l) => (
              <SelectItem key={l} value={l}>
                {l}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={status} onValueChange={setStatus}>
          <SelectTrigger className="w-36">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            {STATUSES.map((s) => (
              <SelectItem key={s} value={s}>
                {s}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Button onClick={applyFilters}>Apply</Button>
      </div>

      {/* ── Table ── */}
      <div className="rounded-xl border bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Phone</TableHead>
              <TableHead>Language</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Duration</TableHead>
              <TableHead>State</TableHead>
              <TableHead>Date</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading &&
              Array.from({ length: 5 }).map((_, i) => (
                <TableRow key={i}>
                  {Array.from({ length: 6 }).map((__, j) => (
                    <TableCell key={j}>
                      <Skeleton className="h-4 w-20" />
                    </TableCell>
                  ))}
                </TableRow>
              ))}

            {!isLoading && calls.length === 0 && (
              <TableRow>
                <TableCell
                  colSpan={6}
                  className="py-12 text-center text-muted-foreground"
                >
                  No calls found
                </TableCell>
              </TableRow>
            )}

            {!isLoading &&
              calls.map((call) => (
                <TableRow
                  key={call.call_sid}
                  className="cursor-pointer hover:bg-muted/50"
                  onClick={() => setSelectedCall(call)}
                >
                  <TableCell className="font-medium">
                    {call.phone || "—"}
                  </TableCell>
                  <TableCell>{call.language_detected || "—"}</TableCell>
                  <TableCell>
                    <Badge
                      variant="outline"
                      className={statusColor(call.status)}
                    >
                      {call.status}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    {formatDuration(call.duration_seconds)}
                  </TableCell>
                  <TableCell>{call.state || "—"}</TableCell>
                  <TableCell>{formatDate(call.created_at)}</TableCell>
                </TableRow>
              ))}
          </TableBody>
        </Table>
      </div>

      {/* ── Pagination ── */}
      {!isLoading && total > 0 && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            Page {currentPage} of {totalPages}
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={currentPage <= 1}
              onClick={() => goToPage(currentPage - 1)}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={currentPage >= totalPages}
              onClick={() => goToPage(currentPage + 1)}
            >
              Next
            </Button>
          </div>
        </div>
      )}

      {/* ── Transcript Drawer ── */}
      <Sheet
        open={selectedCall !== null}
        onOpenChange={(open) => {
          if (!open) setSelectedCall(null);
        }}
      >
        <SheetContent side="right" className="sm:max-w-md w-full flex flex-col">
          <SheetHeader className="border-b pb-4 pr-10">
            <SheetTitle className="flex items-center gap-2">
              Conversation Transcript
              {isLive && (
                <span className="inline-flex items-center gap-1.5 text-xs font-medium text-blue-600">
                  <span className="relative flex h-2 w-2">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" />
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500" />
                  </span>
                  Live
                </span>
              )}
            </SheetTitle>
            {selectedCall && (
              <SheetDescription asChild>
                <div className="flex flex-wrap gap-2 text-xs">
                  <span>{selectedCall.phone || "Unknown"}</span>
                  <span>·</span>
                  <span>{selectedCall.language_detected || "—"}</span>
                  <span>·</span>
                  <span>{formatDuration(selectedCall.duration_seconds)}</span>
                  <span>·</span>
                  <Badge
                    variant="outline"
                    className={statusColor(selectedCall.status)}
                  >
                    {selectedCall.status}
                  </Badge>
                  <span>·</span>
                  <span>{formatDate(selectedCall.created_at)}</span>
                </div>
              </SheetDescription>
            )}
            {!transcriptLoading &&
              (transcriptData?.turns.length ?? 0) > 0 &&
              !isEnglish && (
                <Button
                  variant={showTranslation ? "default" : "outline"}
                  size="sm"
                  className="w-fit mt-1"
                  disabled={translate.isPending}
                  onClick={handleTranslate}
                >
                  <Languages className="h-3.5 w-3.5 mr-1.5" />
                  {translate.isPending
                    ? "Translating..."
                    : showTranslation
                      ? "Show Original"
                      : "Translate to English"}
                </Button>
              )}
            {translate.isError && (
              <p className="text-xs text-destructive mt-1">
                Translation failed. Check AWS credentials.
              </p>
            )}
          </SheetHeader>

          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {transcriptLoading &&
              Array.from({ length: 4 }).map((_, i) => (
                <div
                  key={i}
                  className={`flex ${i % 2 === 0 ? "justify-start" : "justify-end"}`}
                >
                  <Skeleton className="h-12 w-3/4 rounded-xl" />
                </div>
              ))}

            {!transcriptLoading &&
              transcriptData?.turns.length === 0 && (
                <p className="text-center text-sm text-muted-foreground py-8">
                  No transcript available for this call.
                </p>
              )}

            {!transcriptLoading &&
              transcriptData?.turns.map((turn) => {
                if (turn.tool_called) {
                  return (
                    <div
                      key={turn.turn_number}
                      className="flex justify-center"
                    >
                      <Badge variant="secondary" className="text-xs font-normal">
                        Called: {turn.tool_called}
                      </Badge>
                    </div>
                  );
                }

                const isUser = turn.speaker === "user";
                const translatedText = translations[turn.turn_number];
                return (
                  <div
                    key={turn.turn_number}
                    className={`flex ${isUser ? "justify-start" : "justify-end"}`}
                  >
                    <div
                      className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm ${
                        isUser
                          ? "bg-muted text-foreground rounded-bl-md"
                          : "bg-primary text-primary-foreground rounded-br-md"
                      }`}
                    >
                      <p className="text-[10px] font-medium opacity-70 mb-0.5">
                        {isUser ? "Farmer" : "Gram Saathi"}
                      </p>
                      <p className="whitespace-pre-wrap">
                        {showTranslation && translatedText
                          ? translatedText
                          : turn.transcript}
                      </p>
                      {showTranslation && translatedText && (
                        <p className="whitespace-pre-wrap mt-1.5 pt-1.5 border-t border-current/10 text-xs opacity-60 italic">
                          {turn.transcript}
                        </p>
                      )}
                    </div>
                  </div>
                );
              })}
            <div ref={chatEndRef} />
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}
