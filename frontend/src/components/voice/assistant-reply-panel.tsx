import {
  Loader2,
  MessageSquareText,
  RotateCcw,
  Square,
  Volume2,
  VolumeX,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { ACTIVE_TEXT_TO_SPEECH_PROVIDER } from "@/lib/text-to-speech";
import type { VoiceCommandResponse } from "@/types/voice";

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

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle className="flex items-center gap-2">
              <MessageSquareText className="size-4" aria-hidden="true" />
              系统回复
            </CardTitle>
            <CardDescription>提交文本后展示后端返回的 reply。</CardDescription>
          </div>
          {response ? (
            <Badge variant={response.need_user_reply ? "secondary" : "outline"}>
              {response.action}
            </Badge>
          ) : null}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="min-h-24 rounded-md bg-secondary/60 p-3 text-sm">
          {isSubmitting ? (
            <div className="flex items-center gap-2 text-muted-foreground">
              <Loader2 className="size-4 animate-spin" aria-hidden="true" />
              正在提交语音命令
            </div>
          ) : response?.reply ? (
            <p className="leading-6 text-foreground">{response.reply}</p>
          ) : (
            <p className="text-muted-foreground">暂无系统回复。</p>
          )}
        </div>
        <div className="rounded-md border bg-background p-3">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="space-y-1">
              <div className="flex items-center gap-2 text-sm font-medium">
                {isTtsEnabled ? (
                  <Volume2 className="size-4" aria-hidden="true" />
                ) : (
                  <VolumeX className="size-4" aria-hidden="true" />
                )}
                语音播报
              </div>
              <p className="text-xs text-muted-foreground">
                {getTtsStatusText({
                  isEnabled: isTtsEnabled,
                  isSpeaking: isTtsSpeaking,
                  isSupported: isTtsSupported,
                })}
              </p>
            </div>
            <div className="grid grid-cols-2 gap-2 sm:flex">
              <Button
                type="button"
                variant={isTtsEnabled ? "default" : "outline"}
                size="sm"
                disabled={isTtsSupported === false}
                aria-pressed={isTtsEnabled}
                onClick={() => onToggleTts(!isTtsEnabled)}
              >
                {isTtsEnabled ? "已开启" : "已关闭"}
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={!canReplay}
                onClick={onReplay}
              >
                <RotateCcw className="size-4" aria-hidden="true" />
                重播
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={!isTtsSpeaking}
                onClick={onStopSpeaking}
              >
                <Square className="size-4" aria-hidden="true" />
                停止
              </Button>
            </div>
          </div>
          <p className="mt-3 text-xs text-muted-foreground">
            当前使用 {ACTIVE_TEXT_TO_SPEECH_PROVIDER} TTS。OpenAI
            Text-to-Speech 接入位已预留，当前未启用云端播报。
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

function getTtsStatusText({
  isEnabled,
  isSpeaking,
  isSupported,
}: {
  isEnabled: boolean;
  isSpeaking: boolean;
  isSupported: boolean | null;
}) {
  if (isSupported === false) {
    return "当前浏览器不支持 SpeechSynthesis，仅显示文字回复。";
  }

  if (isSpeaking) {
    return "正在播报最近一次系统回复。";
  }

  return isEnabled ? "后端返回 reply 后会自动播报。" : "自动播报已关闭。";
}
