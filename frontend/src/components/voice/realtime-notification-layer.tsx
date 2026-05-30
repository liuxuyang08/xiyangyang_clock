import { Bell, CheckCircle2, MessageSquareText, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { ReminderNotification } from "@/types/realtime";

type RealtimeNotice = {
  id: string;
  type: "dialog_followup" | "command_completed";
  message: string;
  receivedAt: string;
};

type RealtimeNotificationLayerProps = {
  highlightedEventId: string | null;
  notice: RealtimeNotice | null;
  reminders: ReminderNotification[];
  onDismissNotice: () => void;
  onDismissReminder: (id: string) => void;
  onOpenReminderEvent: (eventId: string) => void;
};

export function RealtimeNotificationLayer({
  highlightedEventId,
  notice,
  reminders,
  onDismissNotice,
  onDismissReminder,
  onOpenReminderEvent,
}: RealtimeNotificationLayerProps) {
  if (!notice && reminders.length === 0) {
    return null;
  }

  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-[min(420px,calc(100vw-2rem))] flex-col gap-3">
      {notice ? (
        <div className="pointer-events-auto rounded-lg border bg-background p-4 shadow-xl">
          <div className="flex items-start justify-between gap-3">
            <div className="flex min-w-0 gap-3">
              {notice.type === "command_completed" ? (
                <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
              ) : (
                <MessageSquareText className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
              )}
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <p className="text-sm font-medium">
                    {notice.type === "command_completed"
                      ? "命令已完成"
                      : "对话追问"}
                  </p>
                  <Badge variant="outline">实时</Badge>
                </div>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">
                  {notice.message}
                </p>
              </div>
            </div>
            <Button
              type="button"
              variant="outline"
              size="icon"
              aria-label="关闭实时消息"
              onClick={onDismissNotice}
            >
              <X className="size-4" aria-hidden="true" />
            </Button>
          </div>
        </div>
      ) : null}

      {reminders.map((reminder) => (
        <div
          key={reminder.id}
          className="pointer-events-auto rounded-lg border bg-background p-4 shadow-xl"
        >
          <div className="flex items-start justify-between gap-3">
            <div className="flex min-w-0 gap-3">
              <Bell className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-sm font-medium">提醒触发</p>
                  {highlightedEventId === reminder.eventId ? (
                    <Badge variant="secondary">已高亮</Badge>
                  ) : null}
                </div>
                <p className="mt-2 text-sm leading-6">{reminder.title}</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {reminder.startTime
                    ? formatReminderTime(reminder.startTime)
                    : reminder.eventId}
                </p>
                <div className="mt-3 flex gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => onOpenReminderEvent(reminder.eventId)}
                  >
                    查看日程
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => onDismissReminder(reminder.id)}
                  >
                    关闭
                  </Button>
                </div>
              </div>
            </div>
            <Button
              type="button"
              variant="outline"
              size="icon"
              aria-label="关闭提醒"
              onClick={() => onDismissReminder(reminder.id)}
            >
              <X className="size-4" aria-hidden="true" />
            </Button>
          </div>
        </div>
      ))}
    </div>
  );
}

function formatReminderTime(value: string) {
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

export type { RealtimeNotice };
