import { useCallback, useEffect, useRef, useState } from "react";

type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;

type SpeechRecognitionLike = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onstart: (() => void) | null;
  onend: (() => void) | null;
  onresult: ((event: SpeechRecognitionResultEventLike) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEventLike) => void) | null;
};

type SpeechRecognitionResultEventLike = {
  resultIndex: number;
  results: {
    length: number;
    [index: number]: {
      isFinal: boolean;
      [index: number]: {
        transcript: string;
      };
    };
  };
};

type SpeechRecognitionErrorEventLike = {
  error: string;
};

type SpeechRecognitionWindow = Window & {
  SpeechRecognition?: SpeechRecognitionConstructor;
  webkitSpeechRecognition?: SpeechRecognitionConstructor;
};

export function useSpeechRecognition() {
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const finalTranscriptRef = useRef("");
  const [isSupported, setIsSupported] = useState<boolean | null>(null);
  const [isListening, setIsListening] = useState(false);
  const [finalTranscript, setFinalTranscript] = useState("");
  const [interimTranscript, setInterimTranscript] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setIsSupported(Boolean(getSpeechRecognitionConstructor()));

    return () => {
      recognitionRef.current?.abort();
      recognitionRef.current = null;
    };
  }, []);

  const start = useCallback(() => {
    const SpeechRecognition = getSpeechRecognitionConstructor();
    if (!SpeechRecognition) {
      setIsSupported(false);
      setError("当前浏览器不支持 Web Speech API，请使用手动输入。");
      return;
    }

    recognitionRef.current?.abort();
    finalTranscriptRef.current = "";
    setFinalTranscript("");
    setInterimTranscript("");
    setError(null);

    const recognition = new SpeechRecognition();
    recognition.lang = "zh-CN";
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;
    recognition.onstart = () => {
      setIsListening(true);
    };
    recognition.onend = () => {
      setIsListening(false);
      setInterimTranscript("");
    };
    recognition.onerror = (event) => {
      setError(getSpeechErrorMessage(event.error));
      setIsListening(false);
    };
    recognition.onresult = (event) => {
      let finalChunk = "";
      let interimChunk = "";

      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const result = event.results[index];
        const transcript = result[0]?.transcript ?? "";

        if (result.isFinal) {
          finalChunk += transcript;
        } else {
          interimChunk += transcript;
        }
      }

      if (finalChunk) {
        finalTranscriptRef.current = normalizeTranscript(
          `${finalTranscriptRef.current}${finalChunk}`,
        );
        setFinalTranscript(finalTranscriptRef.current);
      }

      setInterimTranscript(interimChunk.trim());
    };

    recognitionRef.current = recognition;

    try {
      recognition.start();
    } catch (startError) {
      setError(
        startError instanceof Error
          ? startError.message
          : "语音识别启动失败，请重试或手动输入。",
      );
      setIsListening(false);
    }
  }, []);

  const stop = useCallback(() => {
    recognitionRef.current?.stop();
    setIsListening(false);
  }, []);

  return {
    error,
    finalTranscript,
    interimTranscript,
    isListening,
    isSupported,
    start,
    stop,
  };
}

function getSpeechRecognitionConstructor() {
  if (typeof window === "undefined") {
    return null;
  }

  const speechWindow = window as SpeechRecognitionWindow;
  return (
    speechWindow.SpeechRecognition ||
    speechWindow.webkitSpeechRecognition ||
    null
  );
}

function normalizeTranscript(value: string) {
  return value.replace(/\s+/g, " ").trim();
}

function getSpeechErrorMessage(errorCode: string) {
  const messages: Record<string, string> = {
    "not-allowed": "浏览器拒绝了麦克风权限，请授权后重试，或使用手动输入。",
    "no-speech": "没有检测到语音，请重新开始识别或手动输入。",
    "audio-capture": "没有可用的麦克风设备，请检查设备后重试。",
    network: "语音识别服务网络异常，请稍后重试或手动输入。",
    aborted: "语音识别已停止。",
  };

  return messages[errorCode] || "语音识别失败，请重试或手动输入。";
}
