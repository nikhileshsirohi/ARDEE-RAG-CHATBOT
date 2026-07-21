import { clearTokens, getAccessToken, getRefreshToken, persistTokens } from "@/lib/auth";
import type {
  ChatAskResponse,
  ChatSession,
  ChatSessionDetail,
  ChatStreamEvent,
  DailyTokenUsageMetric,
  MyTokenUsageSummary,
  RagDocument,
  TokenResponse,
  User,
  UserTokenUsageMetric,
} from "@/lib/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

type RequestOptions = RequestInit & {
  auth?: boolean;
  retry?: boolean;
};

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function parseError(response: Response) {
  try {
    const body = (await response.json()) as { detail?: unknown; message?: unknown };
    if (typeof body.detail === "string") {
      return body.detail;
    }
    if (typeof body.message === "string") {
      return body.message;
    }
    return JSON.stringify(body.detail ?? body);
  } catch {
    return response.statusText || "Request failed";
  }
}

async function refreshAccessToken() {
  const refreshToken = getRefreshToken();
  if (!refreshToken) {
    throw new ApiError("Session expired. Please sign in again.", 401);
  }

  const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });

  if (!response.ok) {
    clearTokens();
    throw new ApiError(await parseError(response), response.status);
  }

  const tokens = (await response.json()) as TokenResponse;
  persistTokens(tokens);
  return tokens.access_token;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers = new Headers(options.headers);

  if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  if (options.auth !== false) {
    const token = getAccessToken();
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
  });

  if (response.status === 401 && options.auth !== false && options.retry !== false) {
    const token = await refreshAccessToken();
    headers.set("Authorization", `Bearer ${token}`);
    return request<T>(path, { ...options, headers, retry: false });
  }

  if (!response.ok) {
    throw new ApiError(await parseError(response), response.status);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

/**
 * POST /chat/ask/stream and dispatch each Server-Sent Event to `onEvent`.
 * Transparently refreshes an expired access token once, mirroring `request`.
 */
export async function askStream(
  payload: { question: string; session_id?: string | null; top_k?: number },
  handlers: { onEvent: (event: ChatStreamEvent) => void; signal?: AbortSignal },
): Promise<void> {
  async function run(retry: boolean): Promise<void> {
    const token = getAccessToken();
    const response = await fetch(`${API_BASE_URL}/chat/ask/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(payload),
      signal: handlers.signal,
    });

    if (response.status === 401 && retry) {
      await refreshAccessToken();
      return run(false);
    }
    if (!response.ok || !response.body) {
      throw new ApiError(await parseError(response), response.status);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      const frames = buffer.split("\n\n");
      buffer = frames.pop() ?? "";
      for (const frame of frames) {
        const data = frame
          .split("\n")
          .filter((line) => line.startsWith("data:"))
          .map((line) => line.slice(5).replace(/^ /, ""))
          .join("\n");
        if (!data) {
          continue;
        }
        try {
          handlers.onEvent(JSON.parse(data) as ChatStreamEvent);
        } catch {
          // Ignore malformed SSE frames.
        }
      }
    }
  }

  await run(true);
}

export const api = {
  register(payload: { email: string; password: string; full_name?: string }) {
    return request<User>("/auth/register", {
      method: "POST",
      auth: false,
      body: JSON.stringify(payload),
    });
  },
  async login(payload: { email: string; password: string }) {
    const form = new URLSearchParams();
    form.set("username", payload.email);
    form.set("password", payload.password);
    const tokens = await request<TokenResponse>("/auth/login", {
      method: "POST",
      auth: false,
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: form,
    });
    persistTokens(tokens);
    return tokens;
  },
  sessions() {
    return request<ChatSession[]>("/chat/sessions");
  },
  session(sessionId: string) {
    return request<ChatSessionDetail>(`/chat/sessions/${sessionId}`);
  },
  renameSession(sessionId: string, title: string) {
    return request<ChatSession>(`/chat/sessions/${sessionId}`, {
      method: "PATCH",
      body: JSON.stringify({ title }),
    });
  },
  deleteSession(sessionId: string) {
    return request<void>(`/chat/sessions/${sessionId}`, {
      method: "DELETE",
    });
  },
  myUsage() {
    return request<MyTokenUsageSummary>("/chat/usage/me");
  },
  ask(payload: { question: string; session_id?: string | null; top_k?: number }) {
    return request<ChatAskResponse>("/chat/ask", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
  documents() {
    return request<RagDocument[]>("/rag/documents");
  },
  uploadDocument(payload: { title: string; file: File }) {
    const form = new FormData();
    form.set("title", payload.title);
    form.set("file", payload.file);
    return request<RagDocument>("/rag/documents", {
      method: "POST",
      body: form,
    });
  },
  updateDocument(documentId: string, payload: { title: string }) {
    return request<RagDocument>(`/rag/documents/${documentId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },
  replaceDocumentFile(documentId: string, file: File) {
    const form = new FormData();
    form.set("file", file);
    return request<RagDocument>(`/rag/documents/${documentId}/file`, {
      method: "PUT",
      body: form,
    });
  },
  deleteDocument(documentId: string) {
    return request<void>(`/rag/documents/${documentId}`, {
      method: "DELETE",
    });
  },
  userTokenUsage(params?: { start_at?: string; end_at?: string }) {
    const search = new URLSearchParams();
    if (params?.start_at) {
      search.set("start_at", params.start_at);
    }
    if (params?.end_at) {
      search.set("end_at", params.end_at);
    }
    const suffix = search.toString() ? `?${search}` : "";
    return request<UserTokenUsageMetric[]>(`/admin/metrics/token-usage/users${suffix}`);
  },
  dailyTokenUsage(params: { start_at: string; end_at: string; user_id?: string }) {
    const search = new URLSearchParams();
    search.set("start_at", params.start_at);
    search.set("end_at", params.end_at);
    if (params.user_id) {
      search.set("user_id", params.user_id);
    }
    return request<DailyTokenUsageMetric[]>(`/admin/metrics/token-usage/daily?${search}`);
  },
};
