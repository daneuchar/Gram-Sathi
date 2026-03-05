"use client";

import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Phone, Globe, PhoneOff } from "lucide-react";
import type { Call } from "@/lib/types";
import { formatDuration } from "@/lib/format";
import { useEndCall } from "@/lib/queries";

interface LiveCallCardProps {
  call: Call;
}

export function LiveCallCard({ call }: LiveCallCardProps) {
  const endCall = useEndCall();

  return (
    <Card className="border-l-[3px] border-l-brand">
      <CardContent className="flex items-center justify-between p-4">
        <div className="flex items-center gap-4">
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-brand/10">
            <Phone className="h-4 w-4 text-brand" />
          </div>
          <div>
            <p className="font-medium">{call.phone || "Unknown"}</p>
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Globe className="h-3 w-3" />
              {call.language_detected || "Detecting..."}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-sm font-medium">
            {formatDuration(call.duration_seconds)}
          </span>
          <Badge
            variant="outline"
            className="text-success border-success/30 bg-success/10"
          >
            {call.status}
          </Badge>
          <Button
            variant="destructive"
            size="sm"
            disabled={endCall.isPending}
            onClick={() => endCall.mutate(call.call_sid)}
          >
            <PhoneOff className="h-3.5 w-3.5 mr-1.5" />
            {endCall.isPending ? "Ending..." : "End Call"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
