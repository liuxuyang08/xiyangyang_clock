import { useEffect } from "react";
import { CalendarClock, Clock, MapPin, Users, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { formatEventTimeRange } from "@/lib/calendar-event";
import type { CalendarEvent } from "@/types/event";

type EventDrawerProps = {
  event: CalendarEvent | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

export function EventDrawer({ event, open, onOpenChange }: EventDrawerProps) {
  useEffect(() => {
    if (!open) {
      return;
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onOpenChange(false);
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [onOpenChange, open]);

  if (!open || !event) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-40">
      <button
        type="button"
        aria-label="关闭日程详情"
        className="absolute inset-0 bg-foreground/15"
        onClick={() => onOpenChange(false)}
      />
      <aside
        aria-labelledby="event-drawer-title"
        role="dialog"
        aria-modal="true"
        className="absolute inset-y-0 right-0 flex w-full max-w-[420px] flex-col border-l bg-background shadow-xl"
      >
        <Card className="flex h-full flex-col rounded-none border-0 shadow-none">
          <CardHeader className="space-y-4 border-b">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0 space-y-2">
                <Badge variant="outline">{event.status}</Badge>
                <CardTitle
                  id="event-drawer-title"
                  className="break-words text-xl leading-7"
                >
                  {event.title}
                </CardTitle>
              </div>
              <Button
                type="button"
                variant="outline"
                size="icon"
                aria-label="关闭"
                onClick={() => onOpenChange(false)}
              >
                <X className="size-4" aria-hidden="true" />
              </Button>
            </div>
          </CardHeader>
          <CardContent className="flex-1 space-y-5 overflow-y-auto p-5">
            <DetailRow
              icon={CalendarClock}
              label="时间"
              value={formatEventTimeRange(event)}
            />
            <DetailRow
              icon={MapPin}
              label="地点"
              value={event.location || "未设置"}
            />
            <DetailRow
              icon={Users}
              label="参与者"
              value={
                event.participants.length > 0
                  ? event.participants.join("、")
                  : "未设置"
              }
            />
            <Separator />
            <section className="space-y-2">
              <h2 className="text-sm font-medium">描述</h2>
              <p className="text-sm leading-6 text-muted-foreground">
                {event.description || "暂无描述。"}
              </p>
            </section>
            <Separator />
            <section className="grid grid-cols-2 gap-3 text-sm">
              <MetaItem label="优先级" value={event.priority} />
              <MetaItem label="来源" value={event.source} />
              <MetaItem label="全天" value={event.is_all_day ? "是" : "否"} />
              <MetaItem label="事件 ID" value={event.id} />
            </section>
          </CardContent>
        </Card>
      </aside>
    </div>
  );
}

type DetailRowProps = {
  icon: typeof Clock;
  label: string;
  value: string;
};

function DetailRow({ icon: Icon, label, value }: DetailRowProps) {
  return (
    <div className="grid grid-cols-[20px_64px_1fr] gap-3 text-sm">
      <Icon className="mt-0.5 size-4 text-muted-foreground" aria-hidden="true" />
      <span className="text-muted-foreground">{label}</span>
      <span className="break-words">{value}</span>
    </div>
  );
}

function MetaItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border bg-muted/30 p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 truncate font-medium">{value}</p>
    </div>
  );
}
