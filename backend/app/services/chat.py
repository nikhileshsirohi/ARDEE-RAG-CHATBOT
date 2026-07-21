"""RAG chatbot orchestration service."""

import time
import uuid
from dataclasses import dataclass

from openai import AsyncOpenAI
from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionMessageParam,
    ChatCompletionUserMessageParam,
)

from app.config import Settings
from app.core.exceptions import NotFoundError
from app.models.rag import ChatMessage, ChatMessageRole, ChatSession
from app.models.user import User
from app.repositories.chat import ChatRepository
from app.repositories.rag_retrieval import HybridSearchResult
from app.services.rag_retrieval import RagRetrievalService
from app.services.semantic_cache import SemanticCacheHit, SemanticCacheService

SYSTEM_PROMPT = """You are an enterprise RAG assistant.
Answer using only the provided context.
If the context is insufficient, say you do not have enough information.
Be concise, accurate, and cite sources using the provided source numbers."""

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
    ) -> GeneratedAnswer:
        """Answer a question from retrieved chunks."""
        context = self._build_context(retrieved_chunks)
        messages = self._build_messages(
            question=question,
            context=context,
            chat_history=chat_history,
        )
        response = await self.client.chat.completions.create(
            model=self.settings.openai_model,
            messages=messages,
            temperature=0.2,
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
    ) -> list[ChatCompletionMessageParam]:
        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": SYSTEM_PROMPT}
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
        retrieval_service: RagRetrievalService,
        answer_service: OpenAIChatAnswerService,
        settings: Settings,
        semantic_cache_service: SemanticCacheService | None = None,
    ) -> None:
        self.chat_repository = chat_repository
        self.retrieval_service = retrieval_service
        self.answer_service = answer_service
        self.settings = settings
        self.semantic_cache_service = semantic_cache_service

    async def ask(
        self,
        *,
        user: User,
        question: str,
        session_id: uuid.UUID | None,
        top_k: int | None,
    ) -> ChatAnswer:
        """Ask the RAG chatbot and persist the conversation."""
        started_at = time.monotonic()
        normalized_question = " ".join(question.split())
        chat_session = await self._get_or_create_session(
            user=user,
            session_id=session_id,
            question=normalized_question,
        )
        query_embedding = await self.retrieval_service.embed_query(normalized_question)
        cache_hit = await self._get_semantic_cache_hit(query_embedding=query_embedding)

        if cache_hit is not None:
            await self.chat_repository.add_message(
                session=chat_session,
                role=ChatMessageRole.USER,
                content=normalized_question,
            )
            latency_ms = round((time.monotonic() - started_at) * 1000)
            assistant_message = await self.chat_repository.add_message(
                session=chat_session,
                role=ChatMessageRole.ASSISTANT,
                content=cache_hit.answer,
                source_citations=cache_hit.source_citations,
                latency_ms=latency_ms,
            )
            embedding_tokens = len(normalized_question.split())
            await self.chat_repository.record_token_usage(
                user_id=user.id,
                session_id=chat_session.id,
                message_id=assistant_message.id,
                model_name=self.settings.openai_model,
                embedding_model_name=self.settings.openai_embedding_model,
                input_tokens=0,
                output_tokens=0,
                embedding_tokens=embedding_tokens,
                request_metadata={
                    "semantic_cache_hit": True,
                    "semantic_cache_similarity": cache_hit.similarity,
                },
            )
            return ChatAnswer(
                session_id=chat_session.id,
                message_id=assistant_message.id,
                answer=cache_hit.answer,
                source_citations=cache_hit.source_citations,
                input_tokens=0,
                output_tokens=0,
                total_tokens=embedding_tokens,
                latency_ms=latency_ms,
                semantic_cache_hit=True,
                semantic_cache_similarity=cache_hit.similarity,
            )

        retrieved_chunks = await self.retrieval_service.search_by_embedding(
            query_embedding=query_embedding,
            top_k=top_k,
        )
        filtered_chunks = self._filter_retrieved_chunks(retrieved_chunks)
        is_low_confidence = len(filtered_chunks) == 0

        if is_low_confidence:
            citations: list[dict[str, object]] = []
            generated_answer = GeneratedAnswer(
                answer=LOW_CONFIDENCE_ANSWER,
                input_tokens=0,
                output_tokens=0,
            )
        else:
            chat_history = await self.chat_repository.list_recent_session_messages(
                session_id=chat_session.id,
                limit=self.settings.chat_history_messages_limit,
            )
            citations = self._build_citations(filtered_chunks)

        await self.chat_repository.add_message(
            session=chat_session,
            role=ChatMessageRole.USER,
            content=normalized_question,
        )

        if not is_low_confidence:
            generated_answer = await self.answer_service.answer_question(
                question=normalized_question,
                retrieved_chunks=filtered_chunks,
                chat_history=chat_history,
            )
            await self._set_semantic_cache(
                query=normalized_question,
                query_embedding=query_embedding,
                generated_answer=generated_answer,
                citations=citations,
            )
        latency_ms = round((time.monotonic() - started_at) * 1000)

        assistant_message = await self.chat_repository.add_message(
            session=chat_session,
            role=ChatMessageRole.ASSISTANT,
            content=generated_answer.answer,
            source_citations=citations,
            latency_ms=latency_ms,
        )
        embedding_tokens = len(normalized_question.split())
        await self.chat_repository.record_token_usage(
            user_id=user.id,
            session_id=chat_session.id,
            message_id=assistant_message.id,
            model_name=self.settings.openai_model,
            embedding_model_name=self.settings.openai_embedding_model,
            input_tokens=generated_answer.input_tokens,
            output_tokens=generated_answer.output_tokens,
            embedding_tokens=embedding_tokens,
            request_metadata={
                "top_k": top_k or self.settings.rag_top_k,
                "retrieved_chunks": len(retrieved_chunks),
                "retrieved_chunks_after_threshold": len(filtered_chunks),
                "low_confidence": is_low_confidence,
                "min_vector_score": self.settings.rag_min_vector_score,
                "best_hybrid_score": self._best_hybrid_score(retrieved_chunks),
                "best_vector_score": self._best_vector_score(retrieved_chunks),
                "best_keyword_score": self._best_keyword_score(retrieved_chunks),
                "semantic_cache_hit": False,
            },
        )

        return ChatAnswer(
            session_id=chat_session.id,
            message_id=assistant_message.id,
            answer=generated_answer.answer,
            source_citations=citations,
            input_tokens=generated_answer.input_tokens,
            output_tokens=generated_answer.output_tokens,
            total_tokens=generated_answer.input_tokens
            + generated_answer.output_tokens
            + embedding_tokens,
            latency_ms=latency_ms,
            semantic_cache_hit=False,
            semantic_cache_similarity=None,
        )

    async def _get_or_create_session(
        self,
        *,
        user: User,
        session_id: uuid.UUID | None,
        question: str,
    ) -> ChatSession:
        if session_id is None:
            return await self.chat_repository.create_session(
                user_id=user.id,
                title=question[:80] or "New chat",
            )

        chat_session = await self.chat_repository.get_user_session(
            session_id=session_id,
            user_id=user.id,
        )
        if chat_session is None:
            raise NotFoundError("Chat session not found")
        return chat_session

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
        """Keep only chunks with enough retrieval confidence for generation."""
        return [
            chunk
            for chunk in retrieved_chunks
            if chunk.vector_score >= self.settings.rag_min_vector_score
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
    ) -> SemanticCacheHit | None:
        if self.semantic_cache_service is None:
            return None
        return await self.semantic_cache_service.get(query_embedding=query_embedding)

    async def _set_semantic_cache(
        self,
        *,
        query: str,
        query_embedding: list[float],
        generated_answer: GeneratedAnswer,
        citations: list[dict[str, object]],
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
        )
