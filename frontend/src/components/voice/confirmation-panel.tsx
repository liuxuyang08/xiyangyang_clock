import { Check, ListChecks, Send, X } from "lucide-react";
import type { FormEvent } from "react";
import { useMemo, useState } from "react";

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
import type {
  VoiceCandidateEvent,
  VoiceCommandResponse,
} from "@/types/voice";

type ConfirmationPanelProps = {
  response: VoiceCommandResponse | null;
  isSubmitting: boolean;
  onSubmitReply: (text: string) => void;
};

export function ConfirmationPanel({
  response,
  isSubmitting,
  onSubmitReply,
}: ConfirmationPanelProps) {
  const [supplementText, setSupplementText] = useState("");
  const missingSlots = useMemo(() => getMissingSlots(response), [response]);
  const candidateEvents = useMemo(() => getCandidateEvents(response), [response]);
  const needsReply = Boolean(response?.need_user_reply);
  const isConfirmAction = Boolean(response && isConfirmationAction(response));
  const canSubmitSupplement = supplementText.trim().length > 0 && !isSubmitting;

  function handleSupplementSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmitSupplement) {
      return;
    }

    onSubmitReply(supplementText.trim());
    setSupplementText("");
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle>对话确认</CardTitle>
            <CardDescription>
              用于补充信息、选择候选日程和确认二次操作。
            </CardDescription>
          </div>
          <Badge variant={needsReply ? "secondary" : "muted"}>
            {needsReply ? "等待回复" : "空闲"}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {needsReply && response ? (
          <div className="rounded-md border bg-background p-3 text-sm leading-6">
            {response.reply}
          </div>
        ) : (
          <div className="rounded-md border border-dashed bg-muted/40 p-3 text-sm text-muted-foreground">
            当前没有等待确认的操作。
          </div>
        )}

        {needsReply && missingSlots.length > 0 ? (
          <form className="space-y-3" onSubmit={handleSupplementSubmit}>
            <div className="space-y-2">
              <label className="text-sm font-medium" htmlFor="supplement-text">
                补充信息
              </label>
              <div className="flex flex-wrap gap-2">
                {missingSlots.map((slot) => (
                  <Badge key={slot} variant="outline">
                    {formatMissingSlot(slot)}
                  </Badge>
                ))}
              </div>
              <Textarea
                id="supplement-text"
                value={supplementText}
                placeholder="请输入需要补充的内容，例如：明天下午三点。"
                className="min-h-20 resize-none"
                disabled={isSubmitting}
                onChange={(event) => setSupplementText(event.target.value)}
              />
            </div>
            <Button className="w-full" disabled={!canSubmitSupplement}>
              <Send className="size-4" aria-hidden="true" />
              提交补充
            </Button>
          </form>
        ) : null}

        {needsReply && candidateEvents.length > 0 ? (
          <div className="space-y-3">
            <div className="flex items-center gap-2 text-sm font-medium">
              <ListChecks className="size-4" aria-hidden="true" />
              候选日程
            </div>
            <div className="space-y-2">
              {candidateEvents.map((candidate, index) => (
                <button
                  key={candidate.id || `${candidate.title}-${index}`}
                  type="button"
                  className="w-full rounded-md border bg-background p-3 text-left text-sm transition-colors hover:bg-accent hover:text-accent-foreground disabled:pointer-events-none disabled:opacity-50"
                  disabled={isSubmitting}
                  onClick={() =>
                    onSubmitReply(buildCandidateSelectionText(candidate, index))
                  }
                >
                  <span className="block font-medium">
                    {index + 1}. {candidate.title || candidate.id}
                  </span>
                  <span className="mt-1 block text-xs text-muted-foreground">
                    {formatCandidateMeta(candidate)}
                  </span>
                </button>
              ))}
            </div>
          </div>
        ) : null}

        {needsReply && isConfirmAction ? (
          <div className="grid grid-cols-2 gap-3">
            <Button disabled={isSubmitting} onClick={() => onSubmitReply("确认")}>
              <Check className="size-4" aria-hidden="true" />
              确认
            </Button>
            <Button
              variant="outline"
              disabled={isSubmitting}
              onClick={() => onSubmitReply("取消")}
            >
              <X className="size-4" aria-hidden="true" />
              取消
            </Button>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function getMissingSlots(response: VoiceCommandResponse | null) {
  const value = response?.data?.missing_slots;
  if (!Array.isArray(value)) {
    return [];
  }

  return value.filter((slot): slot is string => typeof slot === "string");
}

function getCandidateEvents(response: VoiceCommandResponse | null) {
  const value = response?.data?.candidate_events;
  if (!Array.isArray(value)) {
    return [];
  }

  return value.filter(isVoiceCandidateEvent);
}

function isVoiceCandidateEvent(value: unknown): value is VoiceCandidateEvent {
  if (!value || typeof value !== "object") {
    return false;
  }

  return "id" in value && typeof value.id === "string";
}

function isConfirmationAction(response: VoiceCommandResponse) {
  const status = response.data.status;
  return (
    response.action.includes("need_confirm") ||
    response.action.includes("conflict_need_confirm") ||
    status === "need_confirm"
  );
}

function buildCandidateSelectionText(
  candidate: VoiceCandidateEvent,
  index: number,
) {
  const title = candidate.title?.trim();
  if (title) {
    return `选择第${index + 1}个，${candidate.id}，${title}`;
  }

  return `选择第${index + 1}个，${candidate.id}`;
}

function formatCandidateMeta(candidate: VoiceCandidateEvent) {
  const parts = [candidate.id];
  if (candidate.start_time) {
    parts.push(formatCandidateTime(candidate.start_time));
  }

  return parts.join(" · ");
}

function formatCandidateTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function formatMissingSlot(slot: string) {
  const labels: Record<string, string> = {
    intent: "操作类型",
    title: "标题",
    start_time: "开始时间",
    time_text: "时间",
    datetime: "日期时间",
    specific_time: "具体时间",
    date_text: "日期",
    target_event: "目标日程",
    updates: "修改内容",
    confirm_time: "确认时间",
    confirm_range: "确认范围",
  };

  return labels[slot] || slot;
}
