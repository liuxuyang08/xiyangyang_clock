import { Check, Send, X } from "lucide-react";
import type { FormEvent } from "react";
import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
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

  if (!needsReply) return null;

  return (
    <div className="glass-strong rounded-2xl border border-primary/20 px-4 py-3 flex flex-col gap-3 min-w-[260px] max-w-sm">
      <div className="flex items-center gap-2">
        <Badge variant="secondary" className="text-xs shrink-0">等待回复</Badge>
        <p className="text-xs text-muted-foreground truncate">{response?.reply}</p>
      </div>

      {missingSlots.length > 0 ? (
        <form className="flex items-center gap-2" onSubmit={handleSupplementSubmit}>
          <div className="flex flex-wrap gap-1 shrink-0">
            {missingSlots.map((slot) => (
              <Badge key={slot} variant="outline" className="text-xs border-white/10">
                {formatMissingSlot(slot)}
              </Badge>
            ))}
          </div>
          <input
            id="supplement-text"
            type="text"
            value={supplementText}
            placeholder="补充内容…"
            className="flex-1 bg-transparent border-none outline-none text-sm text-foreground placeholder:text-muted-foreground/40 min-w-0"
            disabled={isSubmitting}
            onChange={(e) => setSupplementText(e.target.value)}
          />
          <button
            type="submit"
            disabled={!canSubmitSupplement}
            className="flex size-7 shrink-0 items-center justify-center rounded-full bg-primary/80 hover:bg-primary disabled:opacity-30 transition-all"
            aria-label="提交补充"
          >
            <Send className="size-3 text-white" aria-hidden="true" />
          </button>
        </form>
      ) : null}

      {candidateEvents.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {candidateEvents.map((candidate, index) => (
            <button
              key={candidate.id || `${candidate.title}-${index}`}
              type="button"
              className="rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-left text-xs hover:bg-white/10 disabled:opacity-50 transition-colors"
              disabled={isSubmitting}
              onClick={() => onSubmitReply(buildCandidateSelectionText(candidate, index))}
            >
              <span className="font-medium">{index + 1}. {candidate.title || candidate.id}</span>
              <span className="block text-muted-foreground/60 mt-0.5">{formatCandidateMeta(candidate)}</span>
            </button>
          ))}
        </div>
      ) : null}

      {isConfirmAction ? (
        <div className="flex gap-2">
          <button
            type="button"
            disabled={isSubmitting}
            onClick={() => onSubmitReply("确认")}
            className="flex items-center gap-1.5 rounded-lg bg-primary/80 hover:bg-primary px-3 py-1.5 text-xs text-white font-medium disabled:opacity-50 transition-colors"
          >
            <Check className="size-3" aria-hidden="true" />确认
          </button>
          <button
            type="button"
            disabled={isSubmitting}
            onClick={() => onSubmitReply("取消")}
            className="flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/5 hover:bg-white/10 px-3 py-1.5 text-xs text-muted-foreground font-medium disabled:opacity-50 transition-colors"
          >
            <X className="size-3" aria-hidden="true" />取消
          </button>
        </div>
      ) : null}
    </div>
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
