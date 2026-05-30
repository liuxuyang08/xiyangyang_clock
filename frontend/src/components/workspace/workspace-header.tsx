import { CalendarDays } from "lucide-react";

import { Separator } from "@/components/ui/separator";
import { WebSocketStatusIndicator } from "@/components/voice/websocket-status-indicator";
import type { WebSocketConnectionStatus } from "@/types/realtime";

type WorkspaceHeaderProps = {
  websocketError: string | null;
  websocketStatus: WebSocketConnectionStatus;
  onReconnectWebSocket: () => void;
};

export function WorkspaceHeader({
  websocketError,
  websocketStatus,
  onReconnectWebSocket,
}: WorkspaceHeaderProps) {
  return (
    <header className="relative border-b border-white/8 glass-strong sticky top-0 z-50">
      <div className="mx-auto flex max-w-[1480px] flex-col gap-3 px-4 py-4 md:flex-row md:items-center md:justify-between md:px-6">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex size-10 shrink-0 items-center justify-center rounded-xl glass glow-primary">
            <CalendarDays className="size-5 text-primary" aria-hidden="true" />
          </div>
          <div className="min-w-0">
            <h1 className="truncate text-lg font-bold tracking-tight gradient-text">
              Xiyangyang Clock
            </h1>
            <p className="mt-0.5 truncate text-xs tracking-widest uppercase text-muted-foreground/60">
              语音日程工作台
            </p>
          </div>
        </div>
        <div className="hidden md:block">
          <Separator orientation="vertical" className="h-7" />
        </div>
        <WebSocketStatusIndicator
          error={websocketError}
          status={websocketStatus}
          onReconnect={onReconnectWebSocket}
        />
      </div>
      <div className="absolute bottom-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-primary/40 to-transparent" />
    </header>
  );
}
