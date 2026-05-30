import { WifiOff } from "lucide-react";

import { Badge } from "@/components/ui/badge";

export function WebSocketStatusIndicator() {
  return (
    <div className="flex items-center justify-between gap-3 rounded-md border bg-card px-3 py-2 text-sm md:justify-start">
      <div className="flex items-center gap-2 text-muted-foreground">
        <WifiOff className="size-4" aria-hidden="true" />
        <span>WebSocket</span>
      </div>
      <Badge variant="muted">未连接</Badge>
    </div>
  );
}
