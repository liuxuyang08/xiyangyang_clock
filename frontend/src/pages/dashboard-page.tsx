import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { CalendarPanel } from "@/components/calendar/calendar-panel";
import { EventDrawer } from "@/components/calendar/event-drawer";
import { EventDetailsSidebar } from "@/components/calendar/event-details-sidebar";
import { WorkspaceHeader } from "@/components/workspace/workspace-header";
import { AssistantReplyPanel } from "@/components/voice/assistant-reply-panel";
import { ConfirmationPanel } from "@/components/voice/confirmation-panel";
import {
  RealtimeNotificationLayer,
  type RealtimeNotice,
} from "@/components/voice/realtime-notification-layer";
import { TranscriptPanel } from "@/components/voice/transcript-panel";
import { VoiceInputPanel } from "@/components/voice/voice-input-panel";
import { getApiErrorMessage } from "@/lib/api";
import { useEvents } from "@/hooks/use-events";
import { useSpeechRecognition } from "@/hooks/use-speech-recognition";
import { useSpeechSynthesis } from "@/hooks/use-speech-synthesis";
import { useVoiceWebSocket } from "@/hooks/use-voice-websocket";
import { toFullCalendarEvent } from "@/lib/calendar-event";
import {
  getRealtimeMessageReply,
  isCommandCompletedMessage,
  isDialogFollowupMessage,
  isReminderTriggeredMessage,
} from "@/lib/realtime-message";
import { submitVoiceCommand } from "@/lib/voice-api";
import { getOrCreateVoiceSessionId } from "@/lib/voice-session";
import type { CalendarEvent, CalendarVisibleRange } from "@/types/event";
import type {
  ReminderNotification,
  ReminderTriggeredMessage,
  VoiceRealtimeMessage,
} from "@/types/realtime";
import type { VoiceCommandResponse } from "@/types/voice";

const DEFAULT_USER_ID = "u001";
const HIGHLIGHT_DURATION_MS = 18_000;
const MAX_REMINDER_NOTIFICATIONS = 3;

export function DashboardPage() {
  const [sessionId] = useState(() => getOrCreateVoiceSessionId());
  const [voiceText, setVoiceText] = useState("");
  const [voiceResponse, setVoiceResponse] =
    useState<VoiceCommandResponse | null>(null);
  const [voiceSubmitError, setVoiceSubmitError] = useState<string | null>(null);
  const [isVoiceSubmitting, setIsVoiceSubmitting] = useState(false);
  const [visibleRange, setVisibleRange] = useState<CalendarVisibleRange | null>(
    null,
  );
  const [selectedEvent, setSelectedEvent] = useState<CalendarEvent | null>(null);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [highlightedEventId, setHighlightedEventId] = useState<string | null>(
    null,
  );
  const [reminderNotifications, setReminderNotifications] = useState<
    ReminderNotification[]
  >([]);
  const [realtimeNotice, setRealtimeNotice] = useState<RealtimeNotice | null>(
    null,
  );
  const highlightTimersRef = useRef<number[]>([]);
  const speechRecognition = useSpeechRecognition();
  const textToSpeech = useSpeechSynthesis();
  const { events, error, isLoading, refresh } = useEvents({
    userId: DEFAULT_USER_ID,
    range: visibleRange,
  });
  const calendarEvents = useMemo(
    () => events.map((event) => toFullCalendarEvent(event)),
    [events],
  );

  useEffect(() => {
    if (speechRecognition.finalTranscript) {
      setVoiceText(speechRecognition.finalTranscript);
    }
  }, [speechRecognition.finalTranscript]);

  useEffect(() => {
    return () => {
      highlightTimersRef.current.forEach((timerId) =>
        window.clearTimeout(timerId),
      );
      highlightTimersRef.current = [];
    };
  }, []);

  const highlightEvent = useCallback((eventId: string) => {
    setHighlightedEventId(eventId);
    const timerId = window.setTimeout(() => {
      setHighlightedEventId((currentEventId) =>
        currentEventId === eventId ? null : currentEventId,
      );
    }, HIGHLIGHT_DURATION_MS);
    highlightTimersRef.current.push(timerId);
  }, []);

  const handleRealtimeMessage = useCallback(
    (message: VoiceRealtimeMessage) => {
      if (isReminderTriggeredMessage(message)) {
        const notification = toReminderNotification(message);
        setReminderNotifications((current) => [
          notification,
          ...current.filter((item) => item.eventId !== notification.eventId),
        ].slice(0, MAX_REMINDER_NOTIFICATIONS));
        highlightEvent(notification.eventId);
        textToSpeech.speak(buildReminderSpeech(notification));
        return;
      }

      if (isDialogFollowupMessage(message) || isCommandCompletedMessage(message)) {
        const reply = getRealtimeMessageReply(message);
        if (!reply) {
          return;
        }

        setRealtimeNotice({
          id: `${message.type}-${Date.now()}`,
          type: message.type,
          message: reply,
          receivedAt: new Date().toISOString(),
        });
        textToSpeech.speak(reply);
      }
    },
    [highlightEvent, textToSpeech],
  );

  const websocket = useVoiceWebSocket({
    userId: DEFAULT_USER_ID,
    sessionId,
    onMessage: handleRealtimeMessage,
  });

  const submitVoiceText = useCallback(
    async (text: string) => {
      const commandText = text.trim();
      if (!commandText || isVoiceSubmitting) {
        return;
      }

      setVoiceText(commandText);
      setIsVoiceSubmitting(true);
      setVoiceSubmitError(null);
      setVoiceResponse(null);

      try {
        const response = await submitVoiceCommand({
          user_id: DEFAULT_USER_ID,
          session_id: sessionId,
          text: commandText,
          timezone: getClientTimezone(),
          client_time: new Date().toISOString(),
        });
        setVoiceResponse(response);
        textToSpeech.speak(response.reply);
      } catch (submitError) {
        setVoiceSubmitError(
          getApiErrorMessage(submitError, "语音命令提交失败，请稍后重试。"),
        );
      } finally {
        setIsVoiceSubmitting(false);
      }
    },
    [isVoiceSubmitting, sessionId, textToSpeech],
  );

  const handleVoiceSubmit = useCallback(() => {
    void submitVoiceText(voiceText);
  }, [submitVoiceText, voiceText]);

  const handleRangeChange = useCallback((range: CalendarVisibleRange) => {
    setVisibleRange((current) => {
      if (current?.start === range.start && current.end === range.end) {
        return current;
      }

      return range;
    });
  }, []);

  const handleEventSelect = useCallback((event: CalendarEvent) => {
    setSelectedEvent(event);
    setIsDrawerOpen(true);
  }, []);

  const handleOpenReminderEvent = useCallback(
    (eventId: string) => {
      highlightEvent(eventId);
      const matchingEvent = events.find((event) => event.id === eventId);
      if (matchingEvent) {
        setSelectedEvent(matchingEvent);
        setIsDrawerOpen(true);
      }
    },
    [events, highlightEvent],
  );

  const handleDrawerOpenChange = useCallback((open: boolean) => {
    setIsDrawerOpen(open);
  }, []);

  return (
    <main className="min-h-[100dvh] bg-muted/30 text-foreground">
      <WorkspaceHeader
        websocketError={websocket.lastError}
        websocketStatus={websocket.status}
        onReconnectWebSocket={websocket.reconnectNow}
      />
      <div className="mx-auto grid max-w-[1480px] gap-4 px-4 py-4 md:px-6 md:py-5 xl:grid-cols-[360px_minmax(0,1fr)_340px]">
        <section className="grid content-start gap-4">
          <VoiceInputPanel
            value={voiceText}
            sessionId={sessionId}
            isListening={speechRecognition.isListening}
            isSubmitting={isVoiceSubmitting}
            isSpeechSupported={speechRecognition.isSupported}
            speechError={speechRecognition.error}
            submitError={voiceSubmitError}
            onChange={setVoiceText}
            onStartListening={speechRecognition.start}
            onStopListening={speechRecognition.stop}
            onSubmit={handleVoiceSubmit}
          />
          <TranscriptPanel
            finalText={voiceText}
            interimText={speechRecognition.interimTranscript}
            isListening={speechRecognition.isListening}
          />
          <AssistantReplyPanel
            response={voiceResponse}
            isSubmitting={isVoiceSubmitting}
            isTtsEnabled={textToSpeech.isEnabled}
            isTtsSpeaking={textToSpeech.isSpeaking}
            isTtsSupported={textToSpeech.isSupported}
            onReplay={() => {
              if (voiceResponse?.reply) {
                textToSpeech.speak(voiceResponse.reply, { force: true });
              }
            }}
            onStopSpeaking={textToSpeech.stop}
            onToggleTts={textToSpeech.setEnabled}
          />
          <ConfirmationPanel
            response={voiceResponse}
            isSubmitting={isVoiceSubmitting}
            onSubmitReply={(text) => {
              void submitVoiceText(text);
            }}
          />
        </section>
        <CalendarPanel
          events={calendarEvents}
          error={error}
          highlightedEventId={highlightedEventId}
          isLoading={isLoading}
          onEventSelect={handleEventSelect}
          onRangeChange={handleRangeChange}
          onRetry={refresh}
        />
        <EventDetailsSidebar
          event={selectedEvent}
          onOpenDrawer={() => setIsDrawerOpen(true)}
        />
      </div>
      <EventDrawer
        event={selectedEvent}
        open={isDrawerOpen}
        onOpenChange={handleDrawerOpenChange}
      />
      <RealtimeNotificationLayer
        highlightedEventId={highlightedEventId}
        notice={realtimeNotice}
        reminders={reminderNotifications}
        onDismissNotice={() => setRealtimeNotice(null)}
        onDismissReminder={(id) =>
          setReminderNotifications((current) =>
            current.filter((item) => item.id !== id),
          )
        }
        onOpenReminderEvent={handleOpenReminderEvent}
      />
    </main>
  );
}

function getClientTimezone() {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || "Asia/Shanghai";
}

function toReminderNotification(
  message: ReminderTriggeredMessage,
): ReminderNotification {
  const eventId = message.data.event_id;
  const title = message.data.title?.trim() || "日程提醒";

  return {
    id: `${eventId}-${Date.now()}`,
    eventId,
    title,
    startTime: message.data.start_time || null,
    receivedAt: new Date().toISOString(),
  };
}

function buildReminderSpeech(notification: ReminderNotification) {
  if (!notification.startTime) {
    return `提醒：${notification.title}`;
  }

  return `提醒：${notification.title}，时间是${formatReminderSpeechTime(
    notification.startTime,
  )}`;
}

function formatReminderSpeechTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat("zh-CN", {
    month: "long",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}
