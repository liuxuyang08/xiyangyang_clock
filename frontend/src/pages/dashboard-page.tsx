import { useCallback, useEffect, useMemo, useState } from "react";

import { CalendarPanel } from "@/components/calendar/calendar-panel";
import { EventDrawer } from "@/components/calendar/event-drawer";
import { EventDetailsSidebar } from "@/components/calendar/event-details-sidebar";
import { WorkspaceHeader } from "@/components/workspace/workspace-header";
import { AssistantReplyPanel } from "@/components/voice/assistant-reply-panel";
import { ConfirmationPanel } from "@/components/voice/confirmation-panel";
import { TranscriptPanel } from "@/components/voice/transcript-panel";
import { VoiceInputPanel } from "@/components/voice/voice-input-panel";
import { getApiErrorMessage } from "@/lib/api";
import { useEvents } from "@/hooks/use-events";
import { useSpeechRecognition } from "@/hooks/use-speech-recognition";
import { useSpeechSynthesis } from "@/hooks/use-speech-synthesis";
import { toFullCalendarEvent } from "@/lib/calendar-event";
import { submitVoiceCommand } from "@/lib/voice-api";
import { getOrCreateVoiceSessionId } from "@/lib/voice-session";
import type { CalendarEvent, CalendarVisibleRange } from "@/types/event";
import type { VoiceCommandResponse } from "@/types/voice";

const DEFAULT_USER_ID = "u001";

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

  const submitVoiceText = useCallback(async (text: string) => {
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
  }, [isVoiceSubmitting, sessionId, textToSpeech]);

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

  const handleDrawerOpenChange = useCallback((open: boolean) => {
    setIsDrawerOpen(open);
  }, []);

  return (
    <main className="min-h-[100dvh] bg-muted/30 text-foreground">
      <WorkspaceHeader />
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
    </main>
  );
}

function getClientTimezone() {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || "Asia/Shanghai";
}
