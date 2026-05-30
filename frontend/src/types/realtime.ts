export type WebSocketConnectionStatus =
  | "idle"
  | "connecting"
  | "connected"
  | "reconnecting"
  | "disconnected"
  | "error";

export type ReminderTriggeredMessage = {
  type: "reminder_triggered";
  user_id?: string;
  data: {
    event_id: string;
    title?: string | null;
    start_time?: string | null;
  };
};

export type DialogFollowupMessage = {
  type: "dialog_followup";
  user_id?: string;
  data?: {
    reply?: string;
    message?: string;
    [key: string]: unknown;
  };
  reply?: string;
  message?: string;
};

export type CommandCompletedMessage = {
  type: "command_completed";
  user_id?: string;
  data?: {
    reply?: string;
    message?: string;
    [key: string]: unknown;
  };
  reply?: string;
  message?: string;
};

export type HeartbeatAckMessage = {
  type: "heartbeat_ack";
  user_id?: string;
  session_id?: string;
  server_time?: string;
};

export type VoiceRealtimeMessage =
  | ReminderTriggeredMessage
  | DialogFollowupMessage
  | CommandCompletedMessage
  | HeartbeatAckMessage
  | {
      type: string;
      [key: string]: unknown;
    };

export type ReminderNotification = {
  id: string;
  eventId: string;
  title: string;
  startTime: string | null;
  receivedAt: string;
};
