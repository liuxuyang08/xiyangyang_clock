import { useCallback, useEffect, useRef, useState } from "react";

import { createVoiceWebSocket } from "@/lib/websocket";
import { parseRealtimeMessage } from "@/lib/realtime-message";
import type {
  VoiceRealtimeMessage,
  WebSocketConnectionStatus,
} from "@/types/realtime";

type UseVoiceWebSocketParams = {
  userId: string;
  sessionId: string;
  onMessage: (message: VoiceRealtimeMessage) => void;
};

const HEARTBEAT_INTERVAL_MS = 25_000;
const MAX_RECONNECT_DELAY_MS = 15_000;

export function useVoiceWebSocket({
  userId,
  sessionId,
  onMessage,
}: UseVoiceWebSocketParams) {
  const onMessageRef = useRef(onMessage);
  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);
  const heartbeatTimerRef = useRef<number | null>(null);
  const reconnectAttemptRef = useRef(0);
  const shouldReconnectRef = useRef(true);
  const [status, setStatus] = useState<WebSocketConnectionStatus>("idle");
  const [lastError, setLastError] = useState<string | null>(null);

  useEffect(() => {
    onMessageRef.current = onMessage;
  }, [onMessage]);

  const clearTimers = useCallback(() => {
    if (reconnectTimerRef.current !== null) {
      window.clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }

    if (heartbeatTimerRef.current !== null) {
      window.clearInterval(heartbeatTimerRef.current);
      heartbeatTimerRef.current = null;
    }
  }, []);

  const sendHeartbeat = useCallback(() => {
    const socket = socketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      return;
    }

    socket.send(
      JSON.stringify({
        type: "heartbeat",
        user_id: userId,
        session_id: sessionId,
        client_time: new Date().toISOString(),
      }),
    );
  }, [sessionId, userId]);

  const connect = useCallback(
    (nextStatus: WebSocketConnectionStatus = "connecting") => {
      clearTimers();
      setStatus(nextStatus);
      setLastError(null);

      const socket = createVoiceWebSocket({ userId, sessionId });
      socketRef.current = socket;

      socket.onopen = () => {
        reconnectAttemptRef.current = 0;
        setStatus("connected");
        sendHeartbeat();
        heartbeatTimerRef.current = window.setInterval(
          sendHeartbeat,
          HEARTBEAT_INTERVAL_MS,
        );
      };

      socket.onmessage = (event) => {
        const message = parseRealtimeMessage(event.data);
        if (message) {
          onMessageRef.current(message);
        }
      };

      socket.onerror = () => {
        setLastError("WebSocket 连接异常。");
        setStatus("error");
      };

      socket.onclose = () => {
        if (heartbeatTimerRef.current !== null) {
          window.clearInterval(heartbeatTimerRef.current);
          heartbeatTimerRef.current = null;
        }
        socketRef.current = null;

        if (!shouldReconnectRef.current) {
          setStatus("disconnected");
          return;
        }

        reconnectAttemptRef.current += 1;
        const delay = Math.min(
          1000 * 2 ** Math.max(0, reconnectAttemptRef.current - 1),
          MAX_RECONNECT_DELAY_MS,
        );
        setStatus("reconnecting");
        reconnectTimerRef.current = window.setTimeout(() => {
          connect("reconnecting");
        }, delay);
      };
    },
    [clearTimers, sendHeartbeat, sessionId, userId],
  );

  const reconnectNow = useCallback(() => {
    shouldReconnectRef.current = true;
    reconnectAttemptRef.current = 0;
    const currentSocket = socketRef.current;
    if (currentSocket) {
      currentSocket.onclose = null;
      currentSocket.close();
      socketRef.current = null;
    }
    clearTimers();
    connect("connecting");
  }, [clearTimers, connect]);

  useEffect(() => {
    shouldReconnectRef.current = true;
    connect("connecting");

    return () => {
      shouldReconnectRef.current = false;
      clearTimers();
      socketRef.current?.close();
      socketRef.current = null;
    };
  }, [clearTimers, connect]);

  return {
    lastError,
    reconnectNow,
    status,
  };
}
