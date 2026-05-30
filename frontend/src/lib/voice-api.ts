import { apiRequest } from "@/lib/api";
import type {
  VoiceCommandRequest,
  VoiceCommandResponse,
} from "@/types/voice";

export function submitVoiceCommand(payload: VoiceCommandRequest) {
  return apiRequest<VoiceCommandResponse>("/api/voice/command", {
    method: "POST",
    body: payload,
  });
}
