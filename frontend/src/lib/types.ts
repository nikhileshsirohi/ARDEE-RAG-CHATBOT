export type UserRole = "ADMIN" | "USER";

export type User = {
  id: string;
  email: string;
  full_name: string | null;
  role: UserRole;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type TokenResponse = {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
};

export type SessionUser = {
  id: string;
  email: string;
  full_name: string | null;
  role: UserRole;
};

export type Bot = {
  id: string;
  name: string;
  description: string | null;
  system_prompt: string;
  is_active: boolean;
  created_by_id: string | null;
  document_count: number;
  ready_document_count: number;
  created_at: string;
  updated_at: string;
};

export type BotDetail = Bot & {
  documents: RagDocument[];
};

export type ChatSession = {
  id: string;
  user_id: string;
  bot_id: string | null;
  title: string;
  last_message_at: string | null;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
  total_tokens: number;
};

export type ChatMessage = {
  id: string;
  session_id: string;
  /** Serialized upper-case by the API: USER | ASSISTANT | SYSTEM. */
  role: "SYSTEM" | "USER" | "ASSISTANT";
  content: string;
  source_citations: Citation[];
  latency_ms: number | null;
  created_at: string;
};

export type Citation = {
  source_number?: number;
  document_title?: string;
  original_filename?: string;
  page_number?: number | null;
  hybrid_score?: number;
  vector_score?: number;
  keyword_score?: number;
  [key: string]: unknown;
};

export type ChatSessionDetail = {
  session: ChatSession;
  messages: ChatMessage[];
};

export type ChatAskResponse = {
  session_id: string;
  message_id: string;
  answer: string;
  source_citations: Citation[];
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  latency_ms: number;
  semantic_cache_hit: boolean;
  semantic_cache_similarity: number | null;
};

export type RagDocument = {
  id: string;
  bot_id: string | null;
  title: string;
  original_filename: string;
  status: string;
  version: number;
  page_count: number | null;
  chunk_count: number;
  uploaded_by_id: string | null;
  processed_at: string | null;
  deleted_at: string | null;
  created_at: string;
  updated_at: string;
};

export type UserTokenUsageMetric = {
  user_id: string;
  full_name: string | null;
  email: string;
  role: UserRole;
  input_tokens: number;
  output_tokens: number;
  embedding_tokens: number;
  total_tokens: number;
  request_count: number;
};

export type BotTokenUsageMetric = {
  bot_id: string | null;
  name: string;
  input_tokens: number;
  output_tokens: number;
  embedding_tokens: number;
  total_tokens: number;
  request_count: number;
};

export type DailyTokenUsageMetric = {
  day: string;
  input_tokens: number;
  output_tokens: number;
  embedding_tokens: number;
  total_tokens: number;
  request_count: number;
};

export type SessionTokenUsageMetric = {
  session_id: string;
  title: string;
  bot_id: string | null;
  bot_name: string | null;
  last_message_at: string | null;
  input_tokens: number;
  output_tokens: number;
  embedding_tokens: number;
  total_tokens: number;
  request_count: number;
};

export type MyTokenUsageSummary = {
  input_tokens: number;
  output_tokens: number;
  embedding_tokens: number;
  total_tokens: number;
  request_count: number;
  session_count: number;
  sessions: SessionTokenUsageMetric[];
};

/** Events emitted by the SSE streaming chat endpoint. */
export type ChatStreamEvent =
  | { type: "meta"; session_id: string }
  | { type: "token"; text: string }
  | ({ type: "done" } & ChatAskResponse)
  | { type: "error"; message: string };
