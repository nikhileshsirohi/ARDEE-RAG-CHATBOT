"""Business service for admin-managed bots."""

import uuid

from app.core.exceptions import NotFoundError
from app.models.rag import Bot, RagDocument
from app.models.user import User
from app.repositories.bot import BotRepository
from app.repositories.rag_document import RagDocumentRepository


class BotService:
    """Coordinates bot lifecycle and its knowledge-base documents."""

    def __init__(
        self,
        bot_repository: BotRepository,
        document_repository: RagDocumentRepository,
    ) -> None:
        self.bot_repository = bot_repository
        self.document_repository = document_repository

    async def create_bot(
        self,
        *,
        name: str,
        description: str | None,
        system_prompt: str,
        created_by: User,
    ) -> Bot:
        """Create a bot owned by the given admin."""
        bot = Bot(
            name=name,
            description=description,
            system_prompt=system_prompt,
            created_by_id=created_by.id,
        )
        created = await self.bot_repository.create(bot)
        created.document_count = 0
        created.ready_document_count = 0
        return created

    async def list_bots(self, *, limit: int, offset: int) -> list[Bot]:
        """List active bots with document counts."""
        return await self.bot_repository.list_active(limit=limit, offset=offset)

    async def get_bot(self, *, bot_id: uuid.UUID) -> Bot:
        """Get one active bot or raise."""
        return await self._get_bot_or_raise(bot_id)

    async def get_bot_documents(self, *, bot_id: uuid.UUID) -> list[RagDocument]:
        """List the knowledge-base documents attached to a bot."""
        await self._get_bot_or_raise(bot_id)
        return await self.document_repository.list_active(limit=200, offset=0, bot_id=bot_id)

    async def update_bot(
        self,
        *,
        bot_id: uuid.UUID,
        name: str | None,
        description: str | None,
        system_prompt: str | None,
        is_active: bool | None,
    ) -> Bot:
        """Update mutable fields on a bot."""
        bot = await self._get_bot_or_raise(bot_id)
        return await self.bot_repository.update(
            bot,
            name=name,
            description=description,
            system_prompt=system_prompt,
            is_active=is_active,
        )

    async def delete_bot(self, *, bot_id: uuid.UUID) -> None:
        """Soft-delete a bot (its usage history and sessions are preserved)."""
        bot = await self._get_bot_or_raise(bot_id)
        await self.bot_repository.soft_delete(bot)

    async def _get_bot_or_raise(self, bot_id: uuid.UUID) -> Bot:
        bot = await self.bot_repository.get_active_by_id(bot_id)
        if bot is None:
            raise NotFoundError("Bot not found")
        return bot
