"""RAG chatbot orchestration service."""

import time
import uuid
from dataclasses import dataclass

from openai import AsyncOpenAI

from app.config import Settings
from app.core.exceptions import NotFoundError
from app.models.rag import ChatMessageRole, ChatSession
from app.models.user import User
from app.repositories.chat import ChatRepository
from app.repositories.rag_retrieval import HybridSearchResult
from app.services.rag_retrieval import RagRetrievalService

SYSTEM_PROMPT = """You are an enterprise RAG assistant.
Answer using only the provided context.
If the context is insufficient, say you do not have enough information.
Be concise, accurate, and cite sources using the provided source numbers."""


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
    ) -> GeneratedAnswer:
        """Answer a question from retrieved chunks."""
        context = self._build_context(retrieved_chunks)
        response = await self.client.chat.completions.create(
            model=self.settings.openai_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Context:\n{context}\n\nQuestion:\n{question}",
                },
            ],
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


class ChatService:
    """Coordinates retrieval, answer generation, history, and token metrics."""

    def __init__(
        self,
        chat_repository: ChatRepository,
        retrieval_service: RagRetrievalService,
        answer_service: OpenAIChatAnswerService,
        settings: Settings,
    ) -> None:
        self.chat_repository = chat_repository
        self.retrieval_service = retrieval_service
        self.answer_service = answer_service
        self.settings = settings

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

        await self.chat_repository.add_message(
            session=chat_session,
            role=ChatMessageRole.USER,
            content=normalized_question,
        )

        retrieved_chunks = await self.retrieval_service.search(
            query=normalized_question,
            top_k=top_k,
        )
        citations = self._build_citations(retrieved_chunks)
        generated_answer = await self.answer_service.answer_question(
            question=normalized_question,
            retrieved_chunks=retrieved_chunks,
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
