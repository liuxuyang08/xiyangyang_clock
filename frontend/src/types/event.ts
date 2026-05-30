export type CalendarEventStatus = "active" | "deleted" | string;

export type CalendarEventPriority = "low" | "normal" | "high" | string;

export type CalendarEvent = {
  id: string;
  user_id: string;
  title: string;
  description: string | null;
  start_time: string;
  end_time: string | null;
  location: string | null;
  participants: string[];
  priority: CalendarEventPriority;
  status: CalendarEventStatus;
  source: string;
  is_all_day: boolean;
  recurrence_rule: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
};

export type EventListParams = {
  userId: string;
  start: string;
  end: string;
};

export type CalendarVisibleRange = {
  start: string;
  end: string;
};
