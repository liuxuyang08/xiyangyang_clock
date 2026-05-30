import { Loader2, RefreshCcw, Wifi, WifiOff } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { WebSocketConnectionStatus } from "@/types/realtime";

type WebSocketStatusIndicatorProps = {
  error: string | null;
  status: WebSocketConnectionStatus;
  onReconnect: () => void;
};

export function WebSocketStatusIndicator({
  error,
  status,
  onReconnect,
}: WebSocketStatusIndicatorProps) {
  const isConnected = status === "connected";
  const isBusy = status === "connecting" || status === "reconnecting";

  return (
    <div className="flex items-center justify-between gap-3 rounded-md border bg-card px-3 py-2 text-sm md:justify-start">
      <div className="flex items-center gap-2 text-muted-foreground">
        {isBusy ? (
          <Loader2 className="size-4 animate-spin" aria-hidden="true" />
        ) : isConnected ? (
          <Wifi className="size-4" aria-hidden="true" />
        ) : (
          <WifiOff className="size-4" aria-hidden="true" />
        )}
        <span>WebSocket</span>
      </div>
      <Badge variant={isConnected ? "secondary" : "muted"}>
        {getStatusLabel(status)}
      </Badge>
      {!isConnected ? (
        <Button
          type="button"
          variant="outline"
          size="sm"
          title={error || "重新连接"}
          onClick={onReconnect}
        >
          <RefreshCcw className="size-4" aria-hidden="true" />
          重连
        </Button>
      ) : null}
    </div>
  );
}

function getStatusLabel(status: WebSocketConnectionStatus) {
  const labels: Record<WebSocketConnectionStatus, string> = {
    idle: "未连接",
    connecting: "连接中",
    connected: "已连接",
    reconnecting: "重连中",
    disconnected: "已断开",
    error: "异常",
  };

  return labels[status];
}
