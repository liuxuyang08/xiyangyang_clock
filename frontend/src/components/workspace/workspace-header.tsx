import { CalendarDays } from "lucide-react";

import { Separator } from "@/components/ui/separator";
import { WebSocketStatusIndicator } from "@/components/voice/websocket-status-indicator";

export function WorkspaceHeader() {
  return (
    <header className="border-b bg-background">
      <div className="mx-auto flex max-w-[1480px] flex-col gap-3 px-4 py-4 md:flex-row md:items-center md:justify-between md:px-6">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex size-9 shrink-0 items-center justify-center rounded-md border bg-muted">
            <CalendarDays className="size-4" aria-hidden="true" />
          </div>
          <div className="min-w-0">
            <h1 className="truncate text-base font-semibold tracking-normal">
              Xiyangyang Clock
            </h1>
            <p className="mt-0.5 truncate text-sm text-muted-foreground">
              语音日程工作台
            </p>
          </div>
        </div>
        <div className="hidden md:block">
          <Separator orientation="vertical" className="h-7" />
        </div>
        <WebSocketStatusIndicator />
      </div>
    </header>
  );
}
