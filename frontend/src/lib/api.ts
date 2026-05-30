const DEFAULT_API_BASE_URL = "http://localhost:8000";

export type ApiResponse<T> = {
  success: boolean;
  data: T | null;
  message?: string | null;
};

export type ApiRequestOptions = Omit<RequestInit, "body"> & {
  body?: unknown;
};

export class ApiError extends Error {
  readonly status: number;
  readonly payload: unknown;

  constructor(message: string, status: number, payload: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

export function getApiBaseUrl() {
  return import.meta.env.VITE_API_BASE_URL || DEFAULT_API_BASE_URL;
}

export async function apiRequest<T>(
  path: string,
  options: ApiRequestOptions = {},
): Promise<T> {
  const url = new URL(path, getApiBaseUrl());
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");

  let body: BodyInit | undefined;
  if (options.body !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(options.body);
  }

  const response = await fetch(url, {
    ...options,
    headers,
    body,
  });

  const payload = await parseResponse(response);
  if (!response.ok) {
    throw new ApiError(response.statusText, response.status, payload);
  }

  return payload as T;
}

export function getApiErrorMessage(
  error: unknown,
  fallback = "请求失败，请稍后重试。",
) {
  if (error instanceof ApiError) {
    return extractPayloadMessage(error.payload) || error.message || fallback;
  }

  if (error instanceof Error) {
    return error.message || fallback;
  }

  return fallback;
}

async function parseResponse(response: Response) {
  const contentType = response.headers.get("content-type") || "";
  if (response.status === 204) {
    return null;
  }

  if (contentType.includes("application/json")) {
    return response.json();
  }

  return response.text();
}

function extractPayloadMessage(payload: unknown): string | null {
  if (!payload || typeof payload !== "object") {
    return null;
  }

  if ("message" in payload && typeof payload.message === "string") {
    return payload.message;
  }

  if ("detail" in payload) {
    const detail = payload.detail;
    if (typeof detail === "string") {
      return detail;
    }
    if (Array.isArray(detail) && detail.length > 0) {
      return "请求参数不完整或格式不正确。";
    }
  }

  return null;
}
