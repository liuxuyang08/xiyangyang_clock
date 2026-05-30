import type {
  CommandCompletedMessage,
  DialogFollowupMessage,
  ReminderTriggeredMessage,
  VoiceRealtimeMessage,
} from "@/types/realtime";

export function parseRealtimeMessage(rawData: unknown): VoiceRealtimeMessage | null {
  const parsed = typeof rawData === "string" ? safeJsonParse(rawData) : rawData;
  if (!isRecord(parsed)) {
    return null;
  }

  const type = parsed.type;
  if (typeof type !== "string" || !type) {
    return null;
  }

  return parsed as VoiceRealtimeMessage;
}

export function isReminderTriggeredMessage(
  message: VoiceRealtimeMessage,
): message is ReminderTriggeredMessage {
  return (
    message.type === "reminder_triggered" &&
    isRecord(message.data) &&
    typeof message.data.event_id === "string"
  );
}

export function isDialogFollowupMessage(
  message: VoiceRealtimeMessage,
): message is DialogFollowupMessage {
  return message.type === "dialog_followup";
}

export function isCommandCompletedMessage(
  message: VoiceRealtimeMessage,
): message is CommandCompletedMessage {
  return message.type === "command_completed";
}

export function getRealtimeMessageReply(
  message: DialogFollowupMessage | CommandCompletedMessage,
) {
  if (typeof message.reply === "string" && message.reply.trim()) {
    return message.reply.trim();
  }

  if (typeof message.message === "string" && message.message.trim()) {
    return message.message.trim();
  }

  if (
    isRecord(message.data) &&
    typeof message.data.reply === "string" &&
    message.data.reply.trim()
  ) {
    return message.data.reply.trim();
  }

  if (
    isRecord(message.data) &&
    typeof message.data.message === "string" &&
    message.data.message.trim()
  ) {
    return message.data.message.trim();
  }

  return null;
}

function safeJsonParse(value: string) {
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object";
}
