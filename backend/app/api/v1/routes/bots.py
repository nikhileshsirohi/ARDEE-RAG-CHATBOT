"""Bot management and knowledge-base routes.

Any active user can list and view bots (to chat with them); only admins can
create, update, delete bots and manage their knowledge-base documents.
"""

import uuid
from typing import Annotated, cast

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status

from app.api.dependencies.auth import ActiveUserDep, RequireRole, SessionDep
from app.config import get_settings
from app.core.exceptions import NotFoundError
from app.core.redis import get_redis_client
from app.models.user import User, UserRole
from app.repositories.bot import BotRepository
from app.repositories.rag_document import RagDocumentRepository
from app.schemas.rag import (
    BotCreate,
    BotDetailResponse,
    BotResponse,
    BotUpdate,
    RagDocumentResponse,
)
from app.services.bot import BotService
from app.services.pdf_ingestion import (
    LlamaIndexChunker,
    OpenAIEmbeddingService,
    PdfIngestionService,
    PdfTextExtractor,
)
from app.services.pdf_storage import PdfStorageService
from app.services.rag_document import RagDocumentService
from app.services.semantic_cache import RedisLike, SemanticCacheService

router = APIRouter(prefix="/bots", tags=["Bots"])

AdminDep = Annotated[User, Depends(RequireRole(UserRole.ADMIN))]


def get_bot_service(session: SessionDep) -> BotService:
    """Build bot service from request-scoped dependencies."""
    return BotService(
        bot_repository=BotRepository(session),
        document_repository=RagDocumentRepository(session),
    )


BotServiceDep = Annotated[BotService, Depends(get_bot_service)]


def get_document_service(session: SessionDep) -> RagDocumentService:
    """Build document service for bot knowledge-base uploads."""
    settings = get_settings()
    repository = RagDocumentRepository(session)
    return RagDocumentService(
        repository=repository,
        storage_service=PdfStorageService(settings),
        semantic_cache_service=SemanticCacheService(cast(RedisLike, get_redis_client()), settings),
        ingestion_service=PdfIngestionService(
            repository=repository,
            extractor=PdfTextExtractor(),
            chunker=LlamaIndexChunker(settings),
            embedding_service=OpenAIEmbeddingService(settings),
        ),
    )


DocumentServiceDep = Annotated[RagDocumentService, Depends(get_document_service)]


@router.get("", response_model=list[BotResponse], summary="List bots")
async def list_bots(
    _current_user: ActiveUserDep,
    service: BotServiceDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[BotResponse]:
    """List active bots. Available to any authenticated user."""
    bots = await service.list_bots(limit=limit, offset=offset)
    return [BotResponse.model_validate(bot) for bot in bots]


@router.post(
    "",
    response_model=BotResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a bot",
)
async def create_bot(
    payload: BotCreate,
    admin_user: AdminDep,
    service: BotServiceDep,
) -> BotResponse:
    """Create a bot. Admin-only."""
    bot = await service.create_bot(
        name=payload.name,
        description=payload.description,
        system_prompt=payload.system_prompt,
        created_by=admin_user,
    )
    return BotResponse.model_validate(bot)


@router.get("/{bot_id}", response_model=BotDetailResponse, summary="Get a bot with its documents")
async def get_bot(
    bot_id: uuid.UUID,
    current_user: ActiveUserDep,
    service: BotServiceDep,
) -> BotDetailResponse:
    """Get one bot and its knowledge-base documents."""
    bot = await service.get_bot(bot_id=bot_id)
    if not bot.is_active and current_user.role != UserRole.ADMIN:
        raise NotFoundError("Bot not found")
    documents = await service.get_bot_documents(bot_id=bot_id)
    base = BotResponse.model_validate(bot)
    return BotDetailResponse(
        **base.model_dump(),
        documents=[RagDocumentResponse.model_validate(document) for document in documents],
    )


@router.patch("/{bot_id}", response_model=BotResponse, summary="Update a bot")
async def update_bot(
    bot_id: uuid.UUID,
    payload: BotUpdate,
    _admin_user: AdminDep,
    service: BotServiceDep,
) -> BotResponse:
    """Update a bot. Admin-only."""
    bot = await service.update_bot(
        bot_id=bot_id,
        name=payload.name,
        description=payload.description,
        system_prompt=payload.system_prompt,
        is_active=payload.is_active,
    )
    return BotResponse.model_validate(bot)


@router.delete(
    "/{bot_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a bot",
)
async def delete_bot(
    bot_id: uuid.UUID,
    _admin_user: AdminDep,
    service: BotServiceDep,
) -> Response:
    """Soft-delete a bot. Admin-only."""
    await service.delete_bot(bot_id=bot_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{bot_id}/documents",
    response_model=list[RagDocumentResponse],
    summary="List a bot's knowledge-base documents",
)
async def list_bot_documents(
    bot_id: uuid.UUID,
    _current_user: ActiveUserDep,
    service: BotServiceDep,
) -> list[RagDocumentResponse]:
    """List the PDF documents attached to a bot."""
    documents = await service.get_bot_documents(bot_id=bot_id)
    return [RagDocumentResponse.model_validate(document) for document in documents]


@router.post(
    "/{bot_id}/documents",
    response_model=RagDocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a PDF to a bot's knowledge base",
)
async def upload_bot_document(
    bot_id: uuid.UUID,
    admin_user: AdminDep,
    bot_service: BotServiceDep,
    document_service: DocumentServiceDep,
    title: Annotated[str, Form(min_length=1, max_length=255)],
    file: Annotated[UploadFile, File()],
) -> RagDocumentResponse:
    """Upload a PDF into a bot's knowledge base. Admin-only."""
    await bot_service.get_bot(bot_id=bot_id)
    document = await document_service.upload_pdf(
        title=title,
        file=file,
        uploaded_by=admin_user,
        bot_id=bot_id,
    )
    return RagDocumentResponse.model_validate(document)
