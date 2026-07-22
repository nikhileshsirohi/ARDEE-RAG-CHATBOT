"""Repository for bot persistence and knowledge-base document counts."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rag import Bot, RagDocument, RagDocumentStatus


class BotRepository:
    """Database operations for admin-managed bots."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, bot: Bot) -> Bot:
        """Create a bot record."""
        self.session.add(bot)
        await self.session.flush()
        await self.session.refresh(bot)
        return bot

    async def list_active(self, *, limit: int, offset: int) -> list[Bot]:
        """List non-deleted bots (newest first) with document counts attached."""
        stmt: Select[tuple[Bot]] = (
            select(Bot)
            .where(Bot.deleted_at.is_(None))
            .order_by(Bot.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        bots = list(result.scalars().all())
        await self._attach_document_counts(bots)
        return bots

    async def get_active_by_id(self, bot_id: uuid.UUID) -> Bot | None:
        """Get one non-deleted bot with document counts attached."""
        stmt = select(Bot).where(Bot.id == bot_id, Bot.deleted_at.is_(None))
        result = await self.session.execute(stmt)
        bot = result.scalar_one_or_none()
        if bot is not None:
            await self._attach_document_counts([bot])
        return bot

    async def update(
        self,
        bot: Bot,
        *,
        name: str | None = None,
        description: str | None = None,
        system_prompt: str | None = None,
        is_active: bool | None = None,
    ) -> Bot:
        """Update mutable bot fields."""
        if name is not None:
            bot.name = name
        if description is not None:
            bot.description = description
        if system_prompt is not None:
            bot.system_prompt = system_prompt
        if is_active is not None:
            bot.is_active = is_active
        await self.session.flush()
        await self.session.refresh(bot)
        await self._attach_document_counts([bot])
        return bot

    async def soft_delete(self, bot: Bot) -> Bot:
        """Soft-delete a bot so its usage history survives."""
        bot.deleted_at = datetime.now(UTC)
        bot.is_active = False
        await self.session.flush()
        await self.session.refresh(bot)
        return bot

    async def _attach_document_counts(self, bots: list[Bot]) -> None:
        """Populate transient ``document_count``/``ready_document_count`` fields."""
        if not bots:
            return
        bot_ids = [bot.id for bot in bots]
        stmt = (
            select(
                RagDocument.bot_id,
                func.count(RagDocument.id).label("total"),
                func.count(RagDocument.id)
                .filter(RagDocument.status == RagDocumentStatus.READY)
                .label("ready"),
            )
            .where(
                RagDocument.bot_id.in_(bot_ids),
                RagDocument.deleted_at.is_(None),
            )
            .group_by(RagDocument.bot_id)
        )
        result = await self.session.execute(stmt)
        counts = {
            row["bot_id"]: (int(row["total"]), int(row["ready"]))
            for row in result.mappings().all()
        }
        for bot in bots:
            total, ready = counts.get(bot.id, (0, 0))
            bot.document_count = total
            bot.ready_document_count = ready
