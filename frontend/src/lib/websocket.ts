const DEFAULT_WS_URL = "ws://localhost:8000/ws";

export type VoiceWebSocketOptions = {
  userId: string;
  sessionId: string;
};

export function getWebSocketBaseUrl() {
  return import.meta.env.VITE_WS_URL || DEFAULT_WS_URL;
}

export function buildVoiceWebSocketUrl({
  userId,
  sessionId,
}: VoiceWebSocketOptions) {
  const url = new URL(getWebSocketBaseUrl());
  url.searchParams.set("user_id", userId);
  url.searchParams.set("session_id", sessionId);
  return url.toString();
}

export function createVoiceWebSocket(options: VoiceWebSocketOptions) {
  return new WebSocket(buildVoiceWebSocketUrl(options));
}
