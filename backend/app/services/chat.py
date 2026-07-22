"""RAG chatbot orchestration service."""

import time
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Literal

from openai import AsyncOpenAI
from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionMessageParam,
    ChatCompletionUserMessageParam,
)

from app.config import Settings
from app.core.exceptions import NotFoundError
from app.core.metrics import metrics_registry
from app.models.rag import Bot, ChatMessage, ChatMessageRole, ChatSession
from app.models.user import User
from app.repositories.bot import BotRepository
from app.repositories.chat import ChatRepository
from app.repositories.rag_retrieval import HybridSearchResult
from app.services.greeting import is_greeting
from app.services.rag_retrieval import RagRetrievalService
from app.services.semantic_cache import SemanticCacheHit, SemanticCacheService

DEFAULT_SYSTEM_PROMPT = """You are an enterprise RAG assistant.
Answer using only the provided context.
If the context is insufficient, say you do not have enough information.
Be concise, accurate, and cite sources using the provided source numbers."""

GROUNDING_INSTRUCTIONS = """

You must answer using only the provided context below.
If the context is insufficient, say you do not have enough information.
Be concise and accurate, and cite sources using the provided source numbers."""

GREETING_SYSTEM_PROMPT = """You are a friendly assistant for a document Q&A app.
The user sent a greeting or social pleasantry — respond warmly in one short \
sentence and invite them to ask a question about the uploaded documents.
Do not state any facts, figures, or claims, and do not answer questions here."""

LOW_CONFIDENCE_ANSWER = (
    "I do not have enough information in the uploaded documents to answer this question."
)


@dataclass(frozen=True)
class ChatAnswer:
    """Chatbot answer with persistence and metric metadata."""

    session_id: uuid.UUID
    message_id: uuid.UUID
    answer: str
    source_citations: list[dict[str, object]]
    input_tokens: int
    output_tokens: int
    total_tokens: int
    latency_ms: int
    semantic_cache_hit: bool
    semantic_cache_similarity: float | None


@dataclass(frozen=True)
class GeneratedAnswer:
    """OpenAI-generated answer and usage."""

    answer: str
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class AnswerStreamChunk:
    """A single event from the streaming answer generator.

    Text deltas carry ``text``; the terminal usage event carries token counts.
    """

    text: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass
class PreparedTurn:
    """Shared pre-generation state for :meth:`ChatService.ask` and ``ask_stream``.

    Covers bot/session resolution, greeting short-circuit, semantic-cache lookup,
    hybrid retrieval, confidence gating, citations, and chat history. Callers
    only diverge on how the answer is produced (blocking vs streamed) and how
    the response is returned.
    """

    bot: Bot
    chat_session: ChatSession
    question: str
    kind: Literal["greeting", "cache_hit", "low_confidence", "generate"]
    query_embedding: list[float] | None = None
    cache_hit: SemanticCacheHit | None = None
    retrieved_chunks: list[HybridSearchResult] = field(default_factory=list)
    filtered_chunks: list[HybridSearchResult] = field(default_factory=list)
    citations: list[dict[str, object]] = field(default_factory=list)
    chat_history: list[ChatMessage] = field(default_factory=list)
    top_k: int | None = None


class OpenAIChatAnswerService:
    """Generate grounded answers with OpenAI chat completions."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def answer_question(
        self,
        *,
        question: str,
        retrieved_chunks: list[HybridSearchResult],
        chat_history: list[ChatMessage],
        system_prompt: str,
    ) -> GeneratedAnswer:
        """Answer a question from retrieved chunks."""
        context = self._build_context(retrieved_chunks)
        messages = self._build_messages(
            question=question,
            context=context,
            chat_history=chat_history,
            system_prompt=system_prompt,
        )
        started_at = time.monotonic()
        metrics_registry.increment_counter("llm_calls_total")
        try:
            response = await self.client.chat.completions.create(
                model=self.settings.openai_model,
                messages=messages,
                temperature=0.2,
            )
        except Exception:
            metrics_registry.increment_counter("llm_errors_total")
            raise
        finally:
            metrics_registry.observe_histogram(
                "llm_call_duration_seconds",
                time.monotonic() - started_at,
            )

        answer = response.choices[0].message.content or ""
        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0

        return GeneratedAnswer(
            answer=answer.strip(),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    async def answer_greeting(self, *, question: str) -> GeneratedAnswer:
        """Generate a short, friendly reply to a greeting (no document context)."""
        started_at = time.monotonic()
        metrics_registry.increment_counter("llm_calls_total")
        try:
            response = await self.client.chat.completions.create(
                model=self.settings.openai_model,
                messages=[
                    {"role": "system", "content": GREETING_SYSTEM_PROMPT},
                    {"role": "user", "content": question},
                ],
                temperature=0.5,
            )
        except Exception:
            metrics_registry.increment_counter("llm_errors_total")
            raise
        finally:
            metrics_registry.observe_histogram(
                "llm_call_duration_seconds",
                time.monotonic() - started_at,
            )

        answer = response.choices[0].message.content or ""
        usage = response.usage
        return GeneratedAnswer(
            answer=answer.strip(),
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
        )

    async def stream_answer_question(
        self,
        *,
        question: str,
        retrieved_chunks: list[HybridSearchResult],
        chat_history: list[ChatMessage],
        system_prompt: str,
    ) -> AsyncGenerator[AnswerStreamChunk]:
        """Stream a grounded answer token-by-token.

        Yields :class:`AnswerStreamChunk` text deltas as they arrive and a final
        chunk carrying token usage (requested via ``include_usage``).
        """
        context = self._build_context(retrieved_chunks)
        messages = self._build_messages(
            question=question,
            context=context,
            chat_history=chat_history,
            system_prompt=system_prompt,
        )
        started_at = time.monotonic()
        metrics_registry.increment_counter("llm_calls_total")
        try:
            stream = await self.client.chat.completions.create(
                model=self.settings.openai_model,
                messages=messages,
                temperature=0.2,
                stream=True,
                stream_options={"include_usage": True},
            )
            async for chunk in stream:
                if chunk.choices:
                    delta = chunk.choices[0].delta.content
                    if delta:
                        yield AnswerStreamChunk(text=delta)
                if chunk.usage is not None:
                    yield AnswerStreamChunk(
                        input_tokens=chunk.usage.prompt_tokens,
                        output_tokens=chunk.usage.completion_tokens,
                    )
        except Exception:
            metrics_registry.increment_counter("llm_errors_total")
            raise
        finally:
            metrics_registry.observe_histogram(
                "llm_call_duration_seconds",
                time.monotonic() - started_at,
            )

    @staticmethod
    def _build_context(retrieved_chunks: list[HybridSearchResult]) -> str:
        return "\n\n".join(
            (
                f"[Source {index}] {chunk.document_title}"
                f" ({chunk.original_filename}, page {chunk.page_number or 'unknown'})\n"
                f"{chunk.content}"
            )
            for index, chunk in enumerate(retrieved_chunks, start=1)
        )

    @staticmethod
    def _build_messages(
        *,
        question: str,
        context: str,
        chat_history: list[ChatMessage],
        system_prompt: str,
    ) -> list[ChatCompletionMessageParam]:
        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": f"{system_prompt}{GROUNDING_INSTRUCTIONS}"}
        ]

        for message in chat_history:
            if message.role == ChatMessageRole.SYSTEM:
                continue

            if message.role == ChatMessageRole.ASSISTANT:
                assistant_message: ChatCompletionAssistantMessageParam = {
                    "role": "assistant",
                    "content": message.content,
                }
                messages.append(assistant_message)
            else:
                user_message: ChatCompletionUserMessageParam = {
                    "role": "user",
                    "content": message.content,
                }
                messages.append(user_message)

        messages.append(
            {
                "role": "user",
                "content": f"Context:\n{context}\n\nQuestion:\n{question}",
            }
        )
        return messages


class ChatService:
    """Coordinates retrieval, answer generation, history, and token metrics."""

    def __init__(
        self,
        chat_repository: ChatRepository,
        bot_repository: BotRepository,
        retrieval_service: RagRetrievalService,
        answer_service: OpenAIChatAnswerService,
        settings: Settings,
        semantic_cache_service: SemanticCacheService | None = None,
    ) -> None:
        self.chat_repository = chat_repository
        self.bot_repository = bot_repository
        self.retrieval_service = retrieval_service
        self.answer_service = answer_service
        self.settings = settings
        self.semantic_cache_service = semantic_cache_service

    async def ask(
        self,
        *,
        user: User,
        question: str,
        bot_id: uuid.UUID | None = None,
        session_id: uuid.UUID | None = None,
        top_k: int | None = None,
    ) -> ChatAnswer:
        """Ask the RAG chatbot and persist the conversation."""
        started_at = time.monotonic()
        metrics_registry.increment_counter("rag_queries_total")
        try:
            turn = await self._prepare_turn(
                user=user,
                question=question,
                bot_id=bot_id,
                session_id=session_id,
                top_k=top_k,
            )

            if turn.kind == "greeting":
                return await self._answer_greeting(
                    user=user,
                    bot=turn.bot,
                    chat_session=turn.chat_session,
                    question=turn.question,
                    started_at=started_at,
                )

            await self.chat_repository.add_message(
                session=turn.chat_session,
                role=ChatMessageRole.USER,
                content=turn.question,
            )

            if turn.kind == "cache_hit":
                cache_hit = turn.cache_hit
                if cache_hit is None:
                    raise RuntimeError("Prepared cache_hit turn is missing cache data")
                return await self._persist_turn_answer(
                    user=user,
                    bot=turn.bot,
                    chat_session=turn.chat_session,
                    question=turn.question,
                    answer=cache_hit.answer,
                    citations=cache_hit.source_citations,
                    input_tokens=0,
                    output_tokens=0,
                    started_at=started_at,
                    request_metadata={
                        "semantic_cache_hit": True,
                        "semantic_cache_similarity": cache_hit.similarity,
                    },
                    semantic_cache_hit=True,
                    semantic_cache_similarity=cache_hit.similarity,
                )

            if turn.kind == "low_confidence":
                generated_answer = GeneratedAnswer(
                    answer=LOW_CONFIDENCE_ANSWER,
                    input_tokens=0,
                    output_tokens=0,
                )
            else:
                generated_answer = await self.answer_service.answer_question(
                    question=turn.question,
                    retrieved_chunks=turn.filtered_chunks,
                    chat_history=turn.chat_history,
                    system_prompt=turn.bot.system_prompt,
                )
                if turn.query_embedding is None:
                    raise RuntimeError("Prepared generate turn is missing query embedding")
                await self._set_semantic_cache(
                    query=turn.question,
                    query_embedding=turn.query_embedding,
                    generated_answer=generated_answer,
                    citations=turn.citations,
                    bot_id=turn.bot.id,
                )

            return await self._persist_turn_answer(
                user=user,
                bot=turn.bot,
                chat_session=turn.chat_session,
                question=turn.question,
                answer=generated_answer.answer,
                citations=turn.citations,
                input_tokens=generated_answer.input_tokens,
                output_tokens=generated_answer.output_tokens,
                started_at=started_at,
                request_metadata=self._retrieval_request_metadata(turn),
                semantic_cache_hit=False,
                semantic_cache_similarity=None,
            )
        finally:
            metrics_registry.observe_histogram(
                "rag_query_duration_seconds",
                time.monotonic() - started_at,
            )

    async def ask_stream(
        self,
        *,
        user: User,
        question: str,
        bot_id: uuid.UUID | None = None,
        session_id: uuid.UUID | None = None,
        top_k: int | None = None,
    ) -> AsyncGenerator[dict[str, object]]:
        """Ask the RAG chatbot and stream the answer as it is generated.

        Yields plain dict events (``meta`` → ``token`` … → ``done``) that the
        route serializes as Server-Sent Events. Persistence and token metrics
        mirror :meth:`ask`, and are committed explicitly before the final event
        because the response is produced after the request handler returns.
        """
        started_at = time.monotonic()
        metrics_registry.increment_counter("rag_queries_total")
        try:
            turn = await self._prepare_turn(
                user=user,
                question=question,
                bot_id=bot_id,
                session_id=session_id,
                top_k=top_k,
            )
            yield {"type": "meta", "session_id": str(turn.chat_session.id)}

            if turn.kind == "greeting":
                async for event in self._stream_greeting(
                    user=user,
                    bot=turn.bot,
                    chat_session=turn.chat_session,
                    question=turn.question,
                    started_at=started_at,
                ):
                    yield event
                return

            await self.chat_repository.add_message(
                session=turn.chat_session,
                role=ChatMessageRole.USER,
                content=turn.question,
            )

            input_tokens = 0
            output_tokens = 0
            semantic_cache_hit = False
            semantic_cache_similarity: float | None = None

            if turn.kind == "cache_hit":
                cache_hit = turn.cache_hit
                if cache_hit is None:
                    raise RuntimeError("Prepared cache_hit turn is missing cache data")
                citations = cache_hit.source_citations
                answer_text = cache_hit.answer
                semantic_cache_hit = True
                semantic_cache_similarity = cache_hit.similarity
                for piece in self._iter_text_pieces(answer_text):
                    yield {"type": "token", "text": piece}
            elif turn.kind == "low_confidence":
                citations = turn.citations
                answer_text = LOW_CONFIDENCE_ANSWER
                for piece in self._iter_text_pieces(answer_text):
                    yield {"type": "token", "text": piece}
            else:
                citations = turn.citations
                parts: list[str] = []
                async for chunk in self.answer_service.stream_answer_question(
                    question=turn.question,
                    retrieved_chunks=turn.filtered_chunks,
                    chat_history=turn.chat_history,
                    system_prompt=turn.bot.system_prompt,
                ):
                    if chunk.text:
                        parts.append(chunk.text)
                        yield {"type": "token", "text": chunk.text}
                    if chunk.input_tokens is not None:
                        input_tokens = chunk.input_tokens
                        output_tokens = chunk.output_tokens or 0
                answer_text = "".join(parts).strip()
                if turn.query_embedding is None:
                    raise RuntimeError("Prepared generate turn is missing query embedding")
                await self._set_semantic_cache(
                    query=turn.question,
                    query_embedding=turn.query_embedding,
                    generated_answer=GeneratedAnswer(
                        answer=answer_text,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                    ),
                    citations=citations,
                    bot_id=turn.bot.id,
                )

            chat_answer = await self._persist_turn_answer(
                user=user,
                bot=turn.bot,
                chat_session=turn.chat_session,
                question=turn.question,
                answer=answer_text,
                citations=citations,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                started_at=started_at,
                request_metadata={
                    "streamed": True,
                    **self._retrieval_request_metadata(turn),
                },
                semantic_cache_hit=semantic_cache_hit,
                semantic_cache_similarity=semantic_cache_similarity,
            )
            await self.chat_repository.commit()

            yield {
                "type": "done",
                "session_id": str(chat_answer.session_id),
                "message_id": str(chat_answer.message_id),
                "answer": chat_answer.answer,
                "source_citations": chat_answer.source_citations,
                "input_tokens": chat_answer.input_tokens,
                "output_tokens": chat_answer.output_tokens,
                "total_tokens": chat_answer.total_tokens,
                "latency_ms": chat_answer.latency_ms,
                "semantic_cache_hit": chat_answer.semantic_cache_hit,
                "semantic_cache_similarity": chat_answer.semantic_cache_similarity,
            }
        except Exception:
            # Discard the partially-written turn so a question is never persisted
            # without its answer, matching the non-streaming ``ask`` behavior.
            await self.chat_repository.rollback()
            raise
        finally:
            metrics_registry.observe_histogram(
                "rag_query_duration_seconds",
                time.monotonic() - started_at,
            )

    async def _prepare_turn(
        self,
        *,
        user: User,
        question: str,
        bot_id: uuid.UUID | None,
        session_id: uuid.UUID | None,
        top_k: int | None,
    ) -> PreparedTurn:
        """Resolve session context and retrieval state shared by ask paths."""
        normalized_question = " ".join(question.split())
        bot, chat_session = await self._resolve_bot_and_session(
            user=user,
            bot_id=bot_id,
            session_id=session_id,
            question=normalized_question,
        )

        if is_greeting(normalized_question):
            return PreparedTurn(
                bot=bot,
                chat_session=chat_session,
                question=normalized_question,
                kind="greeting",
                top_k=top_k,
            )

        query_embedding = await self.retrieval_service.embed_query(normalized_question)
        cache_hit = await self._get_semantic_cache_hit(
            query_embedding=query_embedding, bot_id=bot.id
        )
        if cache_hit is not None:
            metrics_registry.increment_counter("rag_cache_hits_total")
            return PreparedTurn(
                bot=bot,
                chat_session=chat_session,
                question=normalized_question,
                kind="cache_hit",
                query_embedding=query_embedding,
                cache_hit=cache_hit,
                top_k=top_k,
            )

        metrics_registry.increment_counter("rag_cache_misses_total")
        retrieved_chunks = await self.retrieval_service.search_hybrid(
            query_text=normalized_question,
            query_embedding=query_embedding,
            bot_id=bot.id,
            top_k=top_k,
        )
        filtered_chunks = self._filter_retrieved_chunks(retrieved_chunks)
        if not filtered_chunks:
            metrics_registry.increment_counter("rag_low_confidence_total")
            return PreparedTurn(
                bot=bot,
                chat_session=chat_session,
                question=normalized_question,
                kind="low_confidence",
                query_embedding=query_embedding,
                retrieved_chunks=retrieved_chunks,
                filtered_chunks=filtered_chunks,
                top_k=top_k,
            )

        chat_history = await self.chat_repository.list_recent_session_messages(
            session_id=chat_session.id,
            limit=self.settings.chat_history_messages_limit,
        )
        return PreparedTurn(
            bot=bot,
            chat_session=chat_session,
            question=normalized_question,
            kind="generate",
            query_embedding=query_embedding,
            retrieved_chunks=retrieved_chunks,
            filtered_chunks=filtered_chunks,
            citations=self._build_citations(filtered_chunks),
            chat_history=chat_history,
            top_k=top_k,
        )

    def _retrieval_request_metadata(self, turn: PreparedTurn) -> dict[str, object]:
        """Build token-usage metadata for retrieval-backed turns."""
        if turn.kind == "cache_hit":
            return {
                "semantic_cache_hit": True,
                "top_k": turn.top_k or self.settings.rag_top_k,
            }
        return {
            "top_k": turn.top_k or self.settings.rag_top_k,
            "retrieved_chunks": len(turn.retrieved_chunks),
            "retrieved_chunks_after_threshold": len(turn.filtered_chunks),
            "low_confidence": turn.kind == "low_confidence",
            "min_vector_score": self.settings.rag_min_vector_score,
            "min_hybrid_score": self.settings.rag_min_hybrid_score,
            "best_hybrid_score": self._best_hybrid_score(turn.retrieved_chunks),
            "best_vector_score": self._best_vector_score(turn.retrieved_chunks),
            "best_keyword_score": self._best_keyword_score(turn.retrieved_chunks),
            "semantic_cache_hit": False,
        }

    async def _persist_turn_answer(
        self,
        *,
        user: User,
        bot: Bot,
        chat_session: ChatSession,
        question: str,
        answer: str,
        citations: list[dict[str, object]],
        input_tokens: int,
        output_tokens: int,
        started_at: float,
        request_metadata: dict[str, object],
        semantic_cache_hit: bool,
        semantic_cache_similarity: float | None,
    ) -> ChatAnswer:
        """Persist the assistant reply and token usage for a prepared turn."""
        latency_ms = round((time.monotonic() - started_at) * 1000)
        assistant_message = await self.chat_repository.add_message(
            session=chat_session,
            role=ChatMessageRole.ASSISTANT,
            content=answer,
            source_citations=citations,
            latency_ms=latency_ms,
        )
        embedding_tokens = len(question.split())
        await self.chat_repository.record_token_usage(
            user_id=user.id,
            bot_id=bot.id,
            session_id=chat_session.id,
            message_id=assistant_message.id,
            model_name=self.settings.openai_model,
            embedding_model_name=self.settings.openai_embedding_model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            embedding_tokens=embedding_tokens,
            request_metadata=request_metadata,
        )
        return ChatAnswer(
            session_id=chat_session.id,
            message_id=assistant_message.id,
            answer=answer,
            source_citations=citations,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens + embedding_tokens,
            latency_ms=latency_ms,
            semantic_cache_hit=semantic_cache_hit,
            semantic_cache_similarity=semantic_cache_similarity,
        )

    async def _stream_greeting(
        self,
        *,
        user: User,
        bot: Bot,
        chat_session: ChatSession,
        question: str,
        started_at: float,
    ) -> AsyncGenerator[dict[str, object]]:
        """Stream an LLM greeting reply and persist the turn (no retrieval)."""
        metrics_registry.increment_counter("rag_greetings_total")
        await self.chat_repository.add_message(
            session=chat_session,
            role=ChatMessageRole.USER,
            content=question,
        )
        generated = await self.answer_service.answer_greeting(question=question)
        for piece in self._iter_text_pieces(generated.answer):
            yield {"type": "token", "text": piece}

        latency_ms = round((time.monotonic() - started_at) * 1000)
        assistant_message = await self.chat_repository.add_message(
            session=chat_session,
            role=ChatMessageRole.ASSISTANT,
            content=generated.answer,
            source_citations=[],
            latency_ms=latency_ms,
        )
        await self.chat_repository.record_token_usage(
            user_id=user.id,
            bot_id=bot.id,
            session_id=chat_session.id,
            message_id=assistant_message.id,
            model_name=self.settings.openai_model,
            embedding_model_name=None,
            input_tokens=generated.input_tokens,
            output_tokens=generated.output_tokens,
            embedding_tokens=0,
            request_metadata={"streamed": True, "greeting": True},
        )
        await self.chat_repository.commit()
        yield {
            "type": "done",
            "session_id": str(chat_session.id),
            "message_id": str(assistant_message.id),
            "answer": generated.answer,
            "source_citations": [],
            "input_tokens": generated.input_tokens,
            "output_tokens": generated.output_tokens,
            "total_tokens": generated.input_tokens + generated.output_tokens,
            "latency_ms": latency_ms,
            "semantic_cache_hit": False,
            "semantic_cache_similarity": None,
        }

    @staticmethod
    def _iter_text_pieces(text: str) -> list[str]:
        """Split cached/static answers into word pieces for a streamed feel."""
        words = text.split(" ")
        return [word if index == 0 else f" {word}" for index, word in enumerate(words)]

    async def _answer_greeting(
        self,
        *,
        user: User,
        bot: Bot,
        chat_session: ChatSession,
        question: str,
        started_at: float,
    ) -> ChatAnswer:
        """Persist a greeting turn answered conversationally by the LLM."""
        metrics_registry.increment_counter("rag_greetings_total")
        await self.chat_repository.add_message(
            session=chat_session,
            role=ChatMessageRole.USER,
            content=question,
        )
        generated = await self.answer_service.answer_greeting(question=question)
        latency_ms = round((time.monotonic() - started_at) * 1000)
        assistant_message = await self.chat_repository.add_message(
            session=chat_session,
            role=ChatMessageRole.ASSISTANT,
            content=generated.answer,
            source_citations=[],
            latency_ms=latency_ms,
        )
        await self.chat_repository.record_token_usage(
            user_id=user.id,
            bot_id=bot.id,
            session_id=chat_session.id,
            message_id=assistant_message.id,
            model_name=self.settings.openai_model,
            embedding_model_name=None,
            input_tokens=generated.input_tokens,
            output_tokens=generated.output_tokens,
            embedding_tokens=0,
            request_metadata={"greeting": True},
        )
        return ChatAnswer(
            session_id=chat_session.id,
            message_id=assistant_message.id,
            answer=generated.answer,
            source_citations=[],
            input_tokens=generated.input_tokens,
            output_tokens=generated.output_tokens,
            total_tokens=generated.input_tokens + generated.output_tokens,
            latency_ms=latency_ms,
            semantic_cache_hit=False,
            semantic_cache_similarity=None,
        )

    async def _resolve_bot_and_session(
        self,
        *,
        user: User,
        bot_id: uuid.UUID | None,
        session_id: uuid.UUID | None,
        question: str,
    ) -> tuple[Bot, ChatSession]:
        """Resolve the target bot and chat session for a question.

        For a new session ``bot_id`` must be supplied; for an existing session
        the bot is inferred from the session so a conversation always stays with
        the bot it started with.
        """
        if session_id is None:
            if bot_id is None:
                raise NotFoundError("A bot is required to start a chat")
            bot = await self._get_active_bot_or_raise(bot_id)
            chat_session = await self.chat_repository.create_session(
                user_id=user.id,
                bot_id=bot.id,
                title=question[:80] or "New chat",
            )
            return bot, chat_session

        chat_session = await self.chat_repository.get_user_session(
            session_id=session_id,
            user_id=user.id,
        )
        if chat_session is None:
            raise NotFoundError("Chat session not found")
        if chat_session.bot_id is None:
            raise NotFoundError("This chat session is not linked to a bot")
        bot = await self._get_active_bot_or_raise(chat_session.bot_id)
        return bot, chat_session

    async def _get_active_bot_or_raise(self, bot_id: uuid.UUID) -> Bot:
        bot = await self.bot_repository.get_active_by_id(bot_id)
        if bot is None or not bot.is_active:
            raise NotFoundError("Bot not found")
        return bot

    @staticmethod
    def _build_citations(retrieved_chunks: list[HybridSearchResult]) -> list[dict[str, object]]:
        return [
            {
                "source_number": index,
                "chunk_id": str(chunk.chunk_id),
                "document_id": str(chunk.document_id),
                "document_title": chunk.document_title,
                "original_filename": chunk.original_filename,
                "page_number": chunk.page_number,
                "hybrid_score": chunk.hybrid_score,
                "vector_score": chunk.vector_score,
                "keyword_score": chunk.keyword_score,
            }
            for index, chunk in enumerate(retrieved_chunks, start=1)
        ]

    def _filter_retrieved_chunks(
        self,
        retrieved_chunks: list[HybridSearchResult],
    ) -> list[HybridSearchResult]:
        """Keep only chunks with enough retrieval confidence for generation.

        A chunk qualifies only when the combined retrieval confidence clears
        the hybrid threshold, while still requiring at least one strong signal
        from vector similarity or keyword match. If nothing qualifies the caller
        returns the fixed "not enough information" message instead of calling
        the LLM.
        """
        return [
            chunk
            for chunk in retrieved_chunks
            if chunk.hybrid_score >= self.settings.rag_min_hybrid_score
            and (
                chunk.vector_score >= self.settings.rag_min_vector_score
                or chunk.keyword_score >= self.settings.rag_min_keyword_score
            )
        ]

    @staticmethod
    def _best_hybrid_score(retrieved_chunks: list[HybridSearchResult]) -> float:
        if not retrieved_chunks:
            return 0.0
        return max(chunk.hybrid_score for chunk in retrieved_chunks)

    @staticmethod
    def _best_vector_score(retrieved_chunks: list[HybridSearchResult]) -> float:
        if not retrieved_chunks:
            return 0.0
        return max(chunk.vector_score for chunk in retrieved_chunks)

    @staticmethod
    def _best_keyword_score(retrieved_chunks: list[HybridSearchResult]) -> float:
        if not retrieved_chunks:
            return 0.0
        return max(chunk.keyword_score for chunk in retrieved_chunks)

    async def _get_semantic_cache_hit(
        self,
        *,
        query_embedding: list[float],
        bot_id: uuid.UUID,
    ) -> SemanticCacheHit | None:
        if self.semantic_cache_service is None:
            return None
        return await self.semantic_cache_service.get(
            query_embedding=query_embedding, bot_id=bot_id
        )

    async def _set_semantic_cache(
        self,
        *,
        query: str,
        query_embedding: list[float],
        generated_answer: GeneratedAnswer,
        citations: list[dict[str, object]],
        bot_id: uuid.UUID,
    ) -> None:
        if self.semantic_cache_service is None:
            return
        await self.semantic_cache_service.set(
            query=query,
            query_embedding=query_embedding,
            answer=generated_answer.answer,
            source_citations=citations,
            input_tokens=generated_answer.input_tokens,
            output_tokens=generated_answer.output_tokens,
            bot_id=bot_id,
        )
