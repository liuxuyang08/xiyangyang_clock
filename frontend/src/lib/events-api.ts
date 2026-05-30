import { apiRequest, type ApiRequestOptions, type ApiResponse } from "@/lib/api";
import type { CalendarEvent, EventListParams } from "@/types/event";

export async function listEvents(
  params: EventListParams,
  options: ApiRequestOptions = {},
) {
  const searchParams = new URLSearchParams({
    user_id: params.userId,
    start: params.start,
    end: params.end,
  });

  const response = await apiRequest<ApiResponse<CalendarEvent[]>>(
    `/api/events?${searchParams.toString()}`,
    {
      ...options,
      method: "GET",
    },
  );

  if (!response.success) {
    throw new Error(response.message || "获取日程失败。");
  }

  return response.data ?? [];
}
