import { useCallback, useEffect, useState } from "react";

import { getApiErrorMessage } from "@/lib/api";
import { listEvents } from "@/lib/events-api";
import type { CalendarEvent, CalendarVisibleRange } from "@/types/event";

type UseEventsParams = {
  userId: string;
  range: CalendarVisibleRange | null;
};

export function useEvents({ userId, range }: UseEventsParams) {
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  const refresh = useCallback(() => {
    setReloadKey((current) => current + 1);
  }, []);

  useEffect(() => {
    if (!range) {
      return;
    }

    const controller = new AbortController();
    setIsLoading(true);
    setError(null);

    listEvents(
      {
        userId,
        start: range.start,
        end: range.end,
      },
      {
        signal: controller.signal,
      },
    )
      .then((items) => {
        setEvents(items);
      })
      .catch((requestError: unknown) => {
        if (isAbortError(requestError)) {
          return;
        }

        setError(getApiErrorMessage(requestError, "获取日程失败，请稍后重试。"));
        setEvents([]);
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setIsLoading(false);
        }
      });

    return () => {
      controller.abort();
    };
  }, [range?.end, range?.start, reloadKey, userId]);

  return {
    events,
    error,
    isLoading,
    refresh,
  };
}

function isAbortError(error: unknown) {
  return error instanceof DOMException && error.name === "AbortError";
}
