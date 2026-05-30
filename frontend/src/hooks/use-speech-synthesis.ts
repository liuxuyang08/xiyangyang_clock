import { useCallback, useEffect, useState } from "react";

const TTS_ENABLED_STORAGE_KEY = "xiyangyang.voice.tts_enabled";

type SpeakOptions = {
  force?: boolean;
};

export function useSpeechSynthesis() {
  const [isSupported, setIsSupported] = useState<boolean | null>(null);
  const [isEnabled, setIsEnabled] = useState(() => getInitialEnabledState());
  const [isSpeaking, setIsSpeaking] = useState(false);

  useEffect(() => {
    setIsSupported(hasSpeechSynthesis());

    return () => {
      if (hasSpeechSynthesis()) {
        window.speechSynthesis.cancel();
      }
    };
  }, []);

  const setEnabled = useCallback((enabled: boolean) => {
    setIsEnabled(enabled);
    persistEnabledState(enabled);

    if (!enabled && hasSpeechSynthesis()) {
      window.speechSynthesis.cancel();
      setIsSpeaking(false);
    }
  }, []);

  const speak = useCallback(
    (text: string, options: SpeakOptions = {}) => {
      const normalizedText = text.trim();
      if (!normalizedText || !hasSpeechSynthesis()) {
        return;
      }

      if (!isEnabled && !options.force) {
        return;
      }

      window.speechSynthesis.cancel();

      const utterance = new SpeechSynthesisUtterance(normalizedText);
      utterance.lang = "zh-CN";
      utterance.rate = 1;
      utterance.pitch = 1;
      utterance.voice = pickPreferredVoice(window.speechSynthesis.getVoices());
      utterance.onstart = () => {
        setIsSpeaking(true);
      };
      utterance.onend = () => {
        setIsSpeaking(false);
      };
      utterance.onerror = () => {
        setIsSpeaking(false);
      };

      window.speechSynthesis.speak(utterance);
    },
    [isEnabled],
  );

  const stop = useCallback(() => {
    if (!hasSpeechSynthesis()) {
      return;
    }

    window.speechSynthesis.cancel();
    setIsSpeaking(false);
  }, []);

  return {
    isEnabled,
    isSpeaking,
    isSupported,
    setEnabled,
    speak,
    stop,
  };
}

function hasSpeechSynthesis() {
  return (
    typeof window !== "undefined" &&
    "speechSynthesis" in window &&
    "SpeechSynthesisUtterance" in window
  );
}

function getInitialEnabledState() {
  if (typeof window === "undefined") {
    return true;
  }

  try {
    return window.localStorage.getItem(TTS_ENABLED_STORAGE_KEY) !== "false";
  } catch {
    return true;
  }
}

function persistEnabledState(enabled: boolean) {
  try {
    window.localStorage.setItem(TTS_ENABLED_STORAGE_KEY, String(enabled));
  } catch {
    return;
  }
}

function pickPreferredVoice(voices: SpeechSynthesisVoice[]) {
  return (
    voices.find((voice) => voice.lang === "zh-CN") ||
    voices.find((voice) => voice.lang.startsWith("zh")) ||
    null
  );
}
