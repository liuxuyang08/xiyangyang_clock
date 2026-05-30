const VOICE_SESSION_STORAGE_KEY = "xiyangyang.voice.session_id";

export function getOrCreateVoiceSessionId() {
  try {
    const existingSessionId = window.localStorage.getItem(
      VOICE_SESSION_STORAGE_KEY,
    );
    if (existingSessionId) {
      return existingSessionId;
    }

    const sessionId = createSessionId();
    window.localStorage.setItem(VOICE_SESSION_STORAGE_KEY, sessionId);
    return sessionId;
  } catch {
    return createSessionId();
  }
}

function createSessionId() {
  if (window.crypto?.randomUUID) {
    return window.crypto.randomUUID();
  }

  return `voice-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}
