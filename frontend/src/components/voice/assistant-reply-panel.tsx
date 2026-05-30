import { useEffect, useRef } from "react";
import {
  Loader2,
  RotateCcw,
  Square,
  Volume2,
  VolumeX,
} from "lucide-react";
import gsap from "gsap";
import { TextPlugin } from "gsap/TextPlugin";

import { Badge } from "@/components/ui/badge";
import type { VoiceCommandResponse } from "@/types/voice";

gsap.registerPlugin(TextPlugin);

type AssistantReplyPanelProps = {
  response: VoiceCommandResponse | null;
  isSubmitting: boolean;
  isTtsEnabled: boolean;
  isTtsSpeaking: boolean;
  isTtsSupported: boolean | null;
  onReplay: () => void;
  onStopSpeaking: () => void;
  onToggleTts: (enabled: boolean) => void;
};

export function AssistantReplyPanel({
  response,
  isSubmitting,
  isTtsEnabled,
  isTtsSpeaking,
  isTtsSupported,
  onReplay,
  onStopSpeaking,
  onToggleTts,
}: AssistantReplyPanelProps) {
  const hasReply = Boolean(response?.reply);
  const canReplay = hasReply && isTtsSupported !== false;

  const replyBoxRef = useRef<HTMLDivElement>(null);
  const replyTextRef = useRef<HTMLParagraphElement>(null);

  useEffect(() => {
    if (!replyBoxRef.current) return;
    if (isSubmitting) return;

    if (response?.reply && replyTextRef.current) {
      gsap.fromTo(replyBoxRef.current,
        { opacity: 0, y: 8 },
        { opacity: 1, y: 0, duration: 0.35, ease: "power2.out" }
      );
      gsap.fromTo(replyTextRef.current,
        { text: { value: "" } },
        {
          text: { value: response.reply },
          duration: Math.min(response.reply.length * 0.025, 2.5),
          ease: "none",
          delay: 0.2,
        }
      );
    }
  }, [response?.reply, isSubmitting]);

  return (
    <div className="flex flex-1 items-center gap-2 glass rounded-2xl px-4 py-2.5 min-w-0">
      {/* 回复文字 */}
      <div ref={replyBoxRef} className="flex-1 min-w-0">
        {isSubmitting ? (
          <div className="flex items-center gap-2 text-muted-foreground/60 text-sm">
            <Loader2 className="size-3.5 animate-spin shrink-0" aria-hidden="true" />
            <span className="truncate">正在处理…</span>
          </div>
        ) : response?.reply ? (
          <div className="flex items-center gap-2 min-w-0">
            <p ref={replyTextRef} className="leading-6 text-foreground text-sm flex-1 truncate" />
            {response.action && (
              <Badge variant="outline" className="shrink-0 text-xs border-white/10 text-muted-foreground">
                {response.action}
              </Badge>
            )}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground/40 truncate">助手回复将显示在这里…</p>
        )}
      </div>

      {/* TTS 控制按钮组 */}
      <div className="flex items-center gap-1 shrink-0">
        <button
          type="button"
          disabled={isTtsSupported === false}
          aria-pressed={isTtsEnabled}
          onClick={() => onToggleTts(!isTtsEnabled)}
          className="flex size-8 items-center justify-center rounded-full hover:bg-white/8 transition-colors disabled:opacity-30"
          aria-label={isTtsEnabled ? "关闭语音播报" : "开启语音播报"}
        >
          {isTtsEnabled
            ? <Volume2 className="size-4 text-primary" aria-hidden="true" />
            : <VolumeX className="size-4 text-muted-foreground/50" aria-hidden="true" />
          }
        </button>
        <button
          type="button"
          disabled={!canReplay}
          onClick={onReplay}
          className="flex size-8 items-center justify-center rounded-full hover:bg-white/8 transition-colors disabled:opacity-30"
          aria-label="重播"
        >
          <RotateCcw className="size-4 text-muted-foreground/70" aria-hidden="true" />
        </button>
        <button
          type="button"
          disabled={!isTtsSpeaking}
          onClick={onStopSpeaking}
          className="flex size-8 items-center justify-center rounded-full hover:bg-white/8 transition-colors disabled:opacity-30"
          aria-label="停止播报"
        >
          <Square className="size-4 text-muted-foreground/70" aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}
