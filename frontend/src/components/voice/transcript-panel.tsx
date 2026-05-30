import { FileText, Radio } from "lucide-react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

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
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <FileText className="size-4" aria-hidden="true" />
          识别文本
        </CardTitle>
        <CardDescription>展示最终识别文本和识别中的临时文本。</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="min-h-24 rounded-md border border-dashed bg-muted/40 p-3 text-sm">
          {finalText ? (
            <p className="leading-6 text-foreground">{finalText}</p>
          ) : (
            <p className="text-muted-foreground">暂无最终识别文本。</p>
          )}
        </div>
        {isListening || interimText ? (
          <div className="rounded-md bg-secondary/60 p-3 text-sm">
            <div className="mb-2 flex items-center gap-2 text-muted-foreground">
              <Radio className="size-4" aria-hidden="true" />
              <span>{isListening ? "正在识别" : "临时文本"}</span>
            </div>
            <p className="min-h-5 leading-6 text-foreground">
              {interimText || "等待语音输入。"}
            </p>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
