import { Loader2, Mic, Send, Square } from "lucide-react";
import type { FormEvent } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";

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
  sessionId,
  isListening,
  isSubmitting,
  isSpeechSupported,
  speechError,
  submitError,
  onChange,
  onStartListening,
  onStopListening,
  onSubmit,
}: VoiceInputPanelProps) {
  const canSubmit = value.trim().length > 0 && !isSubmitting;
  const canStartListening =
    isSpeechSupported !== false && !isListening && !isSubmitting;

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (canSubmit) {
      onSubmit();
    }
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle>语音输入</CardTitle>
            <CardDescription>
              使用 Web Speech API 识别语音，也可以手动输入文本。
            </CardDescription>
          </div>
          <Badge variant={isListening ? "secondary" : "muted"}>
            {isListening ? "识别中" : "待输入"}
          </Badge>
        </div>
      </CardHeader>
      <CardContent>
        <form className="space-y-4" onSubmit={handleSubmit}>
          {isSpeechSupported === false ? (
            <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
              当前浏览器不支持 Web Speech API，请使用手动输入文本。
            </div>
          ) : null}
          {speechError ? (
            <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
              {speechError}
            </div>
          ) : null}
          <div className="grid grid-cols-[1fr_auto] gap-3">
            <Button
              className="justify-start"
              disabled={!canStartListening}
              type="button"
              onClick={onStartListening}
            >
              <Mic className="size-4" aria-hidden="true" />
              开始识别
            </Button>
            <Button
              variant="outline"
              size="icon"
              disabled={!isListening}
              type="button"
              aria-label="停止识别"
              onClick={onStopListening}
            >
              <Square className="size-4" aria-hidden="true" />
            </Button>
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium" htmlFor="voice-command-text">
              命令文本
            </label>
            <Textarea
              id="voice-command-text"
              value={value}
              placeholder="例如：明天下午三点提醒我交项目文档。"
              className="min-h-28 resize-none"
              disabled={isSubmitting}
              onChange={(event) => onChange(event.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              session_id 已保存：{sessionId.slice(0, 8)}
            </p>
          </div>
          {submitError ? (
            <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
              {submitError}
            </div>
          ) : null}
          <Button className="w-full justify-center" disabled={!canSubmit}>
            {isSubmitting ? (
              <Loader2 className="size-4 animate-spin" aria-hidden="true" />
            ) : (
              <Send className="size-4" aria-hidden="true" />
            )}
            提交文本
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
