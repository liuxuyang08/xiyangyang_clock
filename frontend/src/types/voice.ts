export type VoiceCommandRequest = {
  user_id: string;
  session_id: string;
  text: string;
  timezone: string;
  client_time: string;
};

export type VoiceCommandResponse = {
  action: string;
  need_user_reply: boolean;
  reply: string;
  data: Record<string, unknown>;
};

export type VoiceCandidateEvent = {
  id: string;
  title?: string | null;
  start_time?: string | null;
};
