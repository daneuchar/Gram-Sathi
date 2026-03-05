"use client";

import { useState } from "react";
import { useUsers } from "@/lib/queries";
import { formatDate } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Progress } from "@/components/ui/progress";
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
import type { UserProfile } from "@/lib/types";

const STATES = [
  "All",
  "Madhya Pradesh",
  "Uttar Pradesh",
  "Bihar",
  "Rajasthan",
  "Maharashtra",
  "Jharkhand",
  "Chhattisgarh",
  "Odisha",
];
const PER_PAGE = 20;

function profileCompleteness(user: UserProfile): number {
  const fields = [
    user.name,
    user.state,
    user.district,
    user.language,
    user.crops,
    user.land_acres,
  ];
  const filled = fields.filter((f) => f !== null && f !== undefined).length;
  return Math.round((filled / 6) * 100);
}

export default function UserProfilesPage() {
  // Filter form state
  const [phone, setPhone] = useState("");
  const [state, setState] = useState("All");

  // Applied query params (only updated on Apply click)
  const [queryParams, setQueryParams] = useState<{
    page: number;
    per_page: number;
    phone?: string;
    state?: string;
  }>({ page: 1, per_page: PER_PAGE });

  // Selected user for side drawer
  const [selectedUser, setSelectedUser] = useState<UserProfile | null>(null);

  const { data, isLoading } = useUsers(queryParams);
  const users = data?.users ?? [];
  const total = data?.total ?? 0;
  const currentPage = data?.page ?? 1;
  const totalPages = Math.max(1, Math.ceil(total / PER_PAGE));

  function applyFilters() {
    setQueryParams({
      page: 1,
      per_page: PER_PAGE,
      ...(phone ? { phone } : {}),
      ...(state !== "All" ? { state } : {}),
    });
  }

  function goToPage(page: number) {
    setQueryParams((prev) => ({ ...prev, page }));
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold tracking-tight">User Profiles</h1>

      {/* ── Filter Row ── */}
      <div className="flex flex-wrap items-end gap-3">
        <div className="w-48">
          <Input
            placeholder="Search by phone/name"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
          />
        </div>

        <Select value={state} onValueChange={setState}>
          <SelectTrigger className="w-44">
            <SelectValue placeholder="State" />
          </SelectTrigger>
          <SelectContent>
            {STATES.map((s) => (
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
              <TableHead>Name</TableHead>
              <TableHead>State</TableHead>
              <TableHead>District</TableHead>
              <TableHead>Language</TableHead>
              <TableHead>Crops</TableHead>
              <TableHead>Calls</TableHead>
              <TableHead>Joined</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading &&
              Array.from({ length: 5 }).map((_, i) => (
                <TableRow key={i}>
                  {Array.from({ length: 8 }).map((__, j) => (
                    <TableCell key={j}>
                      <Skeleton className="h-4 w-20" />
                    </TableCell>
                  ))}
                </TableRow>
              ))}

            {!isLoading && users.length === 0 && (
              <TableRow>
                <TableCell
                  colSpan={8}
                  className="py-12 text-center text-muted-foreground"
                >
                  No users found
                </TableCell>
              </TableRow>
            )}

            {!isLoading &&
              users.map((user) => (
                <TableRow
                  key={user.phone}
                  className="cursor-pointer"
                  onClick={() => setSelectedUser(user)}
                >
                  <TableCell className="font-medium">
                    {user.phone || "—"}
                  </TableCell>
                  <TableCell>{user.name || "—"}</TableCell>
                  <TableCell>{user.state || "—"}</TableCell>
                  <TableCell>{user.district || "—"}</TableCell>
                  <TableCell>{user.language || "—"}</TableCell>
                  <TableCell>{user.crops || "—"}</TableCell>
                  <TableCell>{user.call_count}</TableCell>
                  <TableCell>{formatDate(user.created_at)}</TableCell>
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

      {/* ── User Detail Sheet ── */}
      <Sheet
        open={selectedUser !== null}
        onOpenChange={(open) => {
          if (!open) setSelectedUser(null);
        }}
      >
        <SheetContent side="right">
          <SheetHeader>
            <SheetTitle>
              {selectedUser?.name || "Unknown Farmer"}
            </SheetTitle>
            <SheetDescription>Farmer profile details</SheetDescription>
          </SheetHeader>

          {selectedUser && (
            <div className="space-y-5 px-4">
              <div className="space-y-3">
                <DetailRow label="Phone" value={selectedUser.phone} />
                <DetailRow label="State" value={selectedUser.state || "—"} />
                <DetailRow
                  label="District"
                  value={selectedUser.district || "—"}
                />
                <DetailRow
                  label="Language"
                  value={selectedUser.language || "—"}
                />
                <DetailRow label="Crops" value={selectedUser.crops || "—"} />
                <DetailRow
                  label="Land Acres"
                  value={
                    selectedUser.land_acres !== null
                      ? String(selectedUser.land_acres)
                      : "—"
                  }
                />
                <DetailRow
                  label="Call Count"
                  value={String(selectedUser.call_count)}
                />
              </div>

              {/* Profile Completeness */}
              <div className="space-y-2">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">
                    Profile Completeness
                  </span>
                  <span className="font-medium">
                    {profileCompleteness(selectedUser)}%
                  </span>
                </div>
                <Progress value={profileCompleteness(selectedUser)} />
              </div>
            </div>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium">{value}</span>
    </div>
  );
}
