import { Radio } from "lucide-react";

type TranscriptPanelProps = {
  finalText: string;
  interimText: string;
  isListening: boolean;
};

export function TranscriptPanel({
  finalText,
  interimText,
  isListening,
}: TranscriptPanelProps) {
  const displayText = interimText || finalText;

  return (
    <div className="flex flex-1 items-center gap-2 glass rounded-2xl px-4 py-2.5 min-w-0">
      <Radio
        className={[
          "size-4 shrink-0 transition-colors",
          isListening ? "text-primary animate-pulse" : "text-muted-foreground/40",
        ].join(" ")}
        aria-hidden="true"
      />
      <p className={[
        "flex-1 text-sm truncate",
        displayText ? "text-foreground" : "text-muted-foreground/40",
      ].join(" ")}>
        {displayText || "识别文本将显示在这里…"}
      </p>
      {isListening && (
        <span className="shrink-0 text-xs text-primary/70">识别中</span>
      )}
    </div>
  );
}
