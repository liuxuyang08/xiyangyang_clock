import type {
  DatesSetArg,
  EventClickArg,
  EventContentArg,
} from "@fullcalendar/core";
import FullCalendar from "@fullcalendar/react";
import { AlertCircle, CalendarClock, Loader2, RefreshCcw } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { fullCalendarPlugins } from "@/lib/full-calendar";
import type { FullCalendarEventInput } from "@/lib/calendar-event";
import type { CalendarEvent, CalendarVisibleRange } from "@/types/event";

type CalendarPanelProps = {
  events: FullCalendarEventInput[];
  error: string | null;
  highlightedEventId: string | null;
  isLoading: boolean;
  onEventSelect: (event: CalendarEvent) => void;
  onRangeChange: (range: CalendarVisibleRange) => void;
  onRetry: () => void;
};

export function CalendarPanel({
  events,
  error,
  highlightedEventId,
  isLoading,
  onEventSelect,
  onRangeChange,
  onRetry,
}: CalendarPanelProps) {
  function handleDatesSet(arg: DatesSetArg) {
    onRangeChange({
      start: arg.start.toISOString(),
      end: arg.end.toISOString(),
    });
  }

  function handleEventClick(arg: EventClickArg) {
    const event = arg.event.extendedProps.calendarEvent as
      | CalendarEvent
      | undefined;
    if (event) {
      onEventSelect(event);
    }
  }

  function getEventClassNames(arg: EventContentArg) {
    return arg.event.id === highlightedEventId
      ? ["calendar-event-highlighted"]
      : [];
  }

  return (
    <Card className="min-w-0">
      <CardHeader className="gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <CardTitle className="flex items-center gap-2">
            <CalendarClock className="size-4" aria-hidden="true" />
            日历视图
          </CardTitle>
          <CardDescription>从后端读取当前可见范围内的日程。</CardDescription>
        </div>
        <Badge variant={isLoading ? "secondary" : "outline"}>
          {isLoading ? "加载中" : `${events.length} 个日程`}
        </Badge>
      </CardHeader>
      <CardContent className="space-y-3">
        {error ? (
          <div className="flex flex-col gap-3 rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-start gap-2">
              <AlertCircle
                className="mt-0.5 size-4 shrink-0"
                aria-hidden="true"
              />
              <span>{error}</span>
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={onRetry}
              className="border-destructive/30 text-destructive hover:bg-destructive/10 hover:text-destructive"
            >
              <RefreshCcw className="size-4" aria-hidden="true" />
              重试
            </Button>
          </div>
        ) : null}
        <div className="calendar-shell relative min-h-[620px] rounded-md border bg-background p-3">
          {isLoading ? (
            <div className="absolute inset-x-3 top-3 z-[1] flex items-center gap-2 rounded-md border bg-background/95 px-3 py-2 text-sm text-muted-foreground shadow-xs">
              <Loader2 className="size-4 animate-spin" aria-hidden="true" />
              正在加载日程
            </div>
          ) : null}
          {!isLoading && events.length === 0 && !error ? (
            <div className="pointer-events-none absolute inset-x-6 bottom-6 z-[1] rounded-md border border-dashed bg-background/95 p-4 text-sm text-muted-foreground shadow-xs">
              当前范围暂无日程。
            </div>
          ) : null}
          <FullCalendar
            plugins={fullCalendarPlugins}
            initialView="timeGridWeek"
            headerToolbar={{
              left: "prev,next today",
              center: "title",
              right: "dayGridMonth,timeGridWeek,timeGridDay",
            }}
            height="auto"
            nowIndicator
            selectable={false}
            editable={false}
            events={events}
            datesSet={handleDatesSet}
            eventClassNames={getEventClassNames}
            eventClick={handleEventClick}
          />
        </div>
      </CardContent>
    </Card>
  );
}
