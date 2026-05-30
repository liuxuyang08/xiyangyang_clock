import { Clock, MapPin, PanelRightOpen } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { formatEventTimeRange } from "@/lib/calendar-event";
import type { CalendarEvent } from "@/types/event";

type EventDetailsSidebarProps = {
  event: CalendarEvent | null;
  onOpenDrawer: () => void;
};

export function EventDetailsSidebar({
  event,
  onOpenDrawer,
}: EventDetailsSidebarProps) {
  const detailRows = [
    {
      icon: Clock,
      label: "时间",
      value: event ? formatEventTimeRange(event) : "未选择",
    },
    {
      icon: MapPin,
      label: "地点",
      value: event?.location || "未选择",
    },
  ];

  return (
    <aside className="min-w-0">
      <Card className="xl:sticky xl:top-5">
        <CardHeader>
          <div className="flex items-start justify-between gap-3">
            <div>
              <CardTitle className="flex items-center gap-2">
                <PanelRightOpen className="size-4" aria-hidden="true" />
                日程详情
              </CardTitle>
              <CardDescription>选择日程后在这里查看摘要。</CardDescription>
            </div>
            <Badge variant={event ? "outline" : "muted"}>
              {event ? event.status : "未选择"}
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="rounded-md border border-dashed bg-muted/40 p-4">
            <p className="text-sm font-medium">
              {event ? event.title : "暂无日程详情"}
            </p>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              {event?.description ||
                "点击日历中的日程后，这里会展示标题、时间、地点和操作入口。"}
            </p>
          </div>
          <Separator />
          <div className="space-y-3">
            {detailRows.map((row) => (
              <div
                className="grid grid-cols-[20px_64px_1fr] items-center gap-2 text-sm"
                key={row.label}
              >
                <row.icon
                  className="size-4 text-muted-foreground"
                  aria-hidden="true"
                />
                <span className="text-muted-foreground">{row.label}</span>
                <span className="truncate">{row.value}</span>
              </div>
            ))}
          </div>
          <Separator />
          <div className="grid grid-cols-2 gap-3">
            <Button variant="outline" disabled={!event} onClick={onOpenDrawer}>
              详情
            </Button>
            <Button variant="outline" disabled>
              删除
            </Button>
          </div>
        </CardContent>
      </Card>
    </aside>
  );
}
