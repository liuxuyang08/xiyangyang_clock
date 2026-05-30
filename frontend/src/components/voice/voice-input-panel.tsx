import { useEffect, useRef } from "react";
import { Loader2, Mic, Send, Square } from "lucide-react";
import gsap from "gsap";

type VoiceInputPanelProps = {
  value: string;
  sessionId: string;
  isListening: boolean;
  isSubmitting: boolean;
  isSpeechSupported: boolean | null;
  speechError: string | null;
  submitError: string | null;
  onChange: (value: string) => void;
  onStartListening: () => void;
  onStopListening: () => void;
  onSubmit: () => void;
};

export function VoiceInputPanel({
  value,
  isListening,
  isSubmitting,
  isSpeechSupported,
  onChange,
  onStartListening,
  onStopListening,
  onSubmit,
}: VoiceInputPanelProps) {
  const canSubmit = value.trim().length > 0 && !isSubmitting;

  const barsRef = useRef<SVGGElement>(null);
  const tweenRef = useRef<gsap.core.Tween | null>(null);

  useEffect(() => {
    const bars = barsRef.current?.querySelectorAll("rect");
    if (!bars || bars.length === 0) return;

    if (isListening) {
      tweenRef.current = gsap.to(bars, {
        scaleY: () => Math.random() * 0.75 + 0.25,
        duration: 0.12,
        repeat: -1,
        yoyo: true,
        stagger: { each: 0.04, repeat: -1 },
        transformOrigin: "50% 100%",
        ease: "power1.inOut",
      });
    } else {
      tweenRef.current?.kill();
      gsap.to(bars, { scaleY: 0.25, duration: 0.4, ease: "power2.out" });
    }

    return () => { tweenRef.current?.kill(); };
  }, [isListening]);

  return (
    <div className="flex items-center gap-3 w-full">
      {/* 圆形麦克风按钮 */}
      <button
        type="button"
        disabled={isSpeechSupported === false || isSubmitting}
        onClick={isListening ? onStopListening : onStartListening}
        className={[
          "relative flex size-14 shrink-0 items-center justify-center rounded-full",
          "transition-all duration-300 focus:outline-none",
          isListening
            ? "bg-destructive glow-pulse shadow-lg shadow-destructive/40"
            : "glass glow-primary hover:scale-105 active:scale-95",
        ].join(" ")}
        aria-label={isListening ? "停止识别" : "开始识别"}
      >
        {isListening
          ? <Square className="size-5 text-white" aria-hidden="true" />
          : <Mic className="size-5 text-primary" aria-hidden="true" />
        }
        {isListening && (
          <span className="absolute inset-0 rounded-full animate-ping bg-destructive/25 pointer-events-none" />
        )}
      </button>

      <svg
        width="44"
        height="32"
        viewBox="0 0 44 32"
        className="shrink-0 hidden sm:block"
        aria-hidden="true"
      >
        <g ref={barsRef}>
          {[4, 10, 16, 22, 28, 34, 40].map((x, i) => (
            <rect
              key={i}
              x={x - 1.5}
              y={4}
              width={3}
              height={24}
              rx={1.5}
              className={isListening ? "fill-primary" : "fill-muted-foreground/25"}
              style={{ transformOrigin: `${x}px 28px` }}
            />
          ))}
        </g>
      </svg>

      {/* 输入区域 */}
      <form
        className="flex flex-1 items-center gap-2 glass rounded-2xl px-4 py-2.5"
        onSubmit={(e) => { e.preventDefault(); if (canSubmit) onSubmit(); }}
      >
        <input
          id="voice-command-text"
          type="text"
          value={value}
          placeholder="说话或输入命令，例如：明天下午三点提醒我..."
          className="flex-1 bg-transparent border-none outline-none text-sm text-foreground placeholder:text-muted-foreground/40 min-w-0"
          disabled={isSubmitting}
          onChange={(e) => onChange(e.target.value)}
        />
        <button
          type="submit"
          disabled={!canSubmit}
          className="flex size-8 shrink-0 items-center justify-center rounded-full bg-primary/80 hover:bg-primary disabled:opacity-30 transition-all"
          aria-label="提交"
        >
          {isSubmitting
            ? <Loader2 className="size-3.5 animate-spin text-white" aria-hidden="true" />
            : <Send className="size-3.5 text-white" aria-hidden="true" />
          }
        </button>
      </form>
    </div>
  );
}
