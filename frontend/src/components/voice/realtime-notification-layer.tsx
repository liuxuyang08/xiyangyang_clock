import { useEffect, useRef } from "react";
import { Bell, CheckCircle2, MessageSquareText, X } from "lucide-react";
import gsap from "gsap";

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
  const notifRefs = useRef<Map<string, HTMLDivElement>>(new Map());

  const dismissWithAnimation = (id: string, onDismiss: () => void) => {
    const el = notifRefs.current.get(id);
    if (el) {
      gsap.to(el, {
        x: "110%",
        opacity: 0,
        duration: 0.3,
        ease: "power2.in",
        onComplete: onDismiss,
      });
    } else {
      onDismiss();
    }
  };

  useEffect(() => {
    const allIds = [
      ...(notice ? [notice.id] : []),
      ...reminders.map((r) => r.id),
    ];
    for (const id of allIds) {
      const el = notifRefs.current.get(id);
      if (el) {
        gsap.fromTo(el,
          { x: "100%", opacity: 0 },
          { x: "0%", opacity: 1, duration: 0.4, ease: "back.out(1.2)" }
        );
      }
    }
  }, [notice, reminders]);

  if (!notice && reminders.length === 0) {
    return null;
  }

  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-[min(420px,calc(100vw-2rem))] flex-col gap-3">
      {notice ? (
        <div
          id={`notif-${notice.id}`}
          ref={(el) => {
            if (el) notifRefs.current.set(notice.id, el);
            else notifRefs.current.delete(notice.id);
          }}
          className="pointer-events-auto glass-strong rounded-2xl border border-white/10 p-4 shadow-2xl"
        >
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
              onClick={() => dismissWithAnimation(notice.id, onDismissNotice)}
            >
              <X className="size-4" aria-hidden="true" />
            </Button>
          </div>
        </div>
      ) : null}

      {reminders.map((reminder) => (
        <div
          key={reminder.id}
          id={`notif-${reminder.id}`}
          ref={(el) => {
            if (el) notifRefs.current.set(reminder.id, el);
            else notifRefs.current.delete(reminder.id);
          }}
          className="pointer-events-auto glass-strong rounded-2xl border border-white/10 p-4 shadow-2xl"
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
                    onClick={() => dismissWithAnimation(reminder.id, () => onDismissReminder(reminder.id))}
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
              onClick={() => dismissWithAnimation(reminder.id, () => onDismissReminder(reminder.id))}
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
