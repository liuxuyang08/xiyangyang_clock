import type { EventInput } from "@fullcalendar/core";

import type { CalendarEvent } from "@/types/event";

export type FullCalendarEventInput = EventInput & {
  extendedProps: {
    calendarEvent: CalendarEvent;
  };
};

const priorityColors: Record<string, { background: string; border: string }> = {
  high: {
    background: "oklch(0.577 0.16 27.325)",
    border: "oklch(0.48 0.15 27.325)",
  },
  normal: {
    background: "oklch(0.45 0.08 240)",
    border: "oklch(0.38 0.08 240)",
  },
  low: {
    background: "oklch(0.48 0.08 160)",
    border: "oklch(0.4 0.08 160)",
  },
};

export function toFullCalendarEvent(
  event: CalendarEvent,
): FullCalendarEventInput {
  const colors = priorityColors[event.priority] ?? priorityColors.normal;

  return {
    id: event.id,
    title: event.title,
    start: event.start_time,
    end: event.end_time ?? undefined,
    allDay: event.is_all_day,
    backgroundColor: colors.background,
    borderColor: colors.border,
    textColor: "oklch(0.985 0 0)",
    extendedProps: {
      calendarEvent: event,
    },
  };
}

export function formatEventTimeRange(event: CalendarEvent) {
  const start = formatDateTime(event.start_time);
  if (!event.end_time) {
    return start;
  }

  return `${start} - ${formatDateTime(event.end_time)}`;
}

export function formatDateTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}
