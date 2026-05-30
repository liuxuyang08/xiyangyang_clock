export type TextToSpeechProvider = "browser" | "openai";

export const ACTIVE_TEXT_TO_SPEECH_PROVIDER: TextToSpeechProvider = "browser";

export type OpenAITextToSpeechRequest = {
  text: string;
  voice?: string;
};

export async function synthesizeWithOpenAITextToSpeech(
  _request: OpenAITextToSpeechRequest,
): Promise<ArrayBuffer> {
  throw new Error("OpenAI Text-to-Speech is reserved but not implemented.");
}
