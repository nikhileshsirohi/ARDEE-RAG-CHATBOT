"""Seed the database with baseline admin and user accounts for staging.

Creates 2 admins and 6 regular users. The script is **idempotent** — accounts
whose email already exists are left untouched — so it is safe to re-run.

Safety:
    Refuses to run against a production environment (``APP_ENV=production``)
    unless ``--force`` is passed, to avoid seeding real deployments.

Usage (from the ``backend`` directory)::

    uv run python -m scripts.seed_staging
    make seed-staging                                     # from the repo root
    SEED_PASSWORD='YourStagingPass1!' uv run python -m scripts.seed_staging
    uv run python -m scripts.seed_staging --password 'YourStagingPass1!'
    uv run python -m scripts.seed_staging --force         # allow non-staging envs

All seeded accounts share one password (printed on completion) so testers can
sign in quickly. Change it with --password / SEED_PASSWORD.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass

from sqlalchemy import select, update

from app.config import get_settings
from app.core.database import _get_session_factory as get_session_factory
from app.core.database import close_db, init_db
from app.core.logging import setup_logging
from app.core.security import get_password_hash
from app.models.rag import Bot, ChatSession, RagDocument
from app.models.user import User, UserRole
from app.repositories.user import UserRepository

DEFAULT_PASSWORD = "StagingPass123!"

DEFAULT_BOT_NAME = "General Knowledge Assistant"
DEFAULT_BOT_DESCRIPTION = "Answers questions from the uploaded knowledge base."
DEFAULT_BOT_SYSTEM_PROMPT = (
    "You are a helpful enterprise assistant. Answer the user's questions "
    "accurately and concisely using the bot's knowledge base."
)


@dataclass(frozen=True)
class SeedUser:
    """A single account to seed."""

    email: str
    full_name: str
    role: UserRole


# 2 admins + 6 users.
SEED_USERS: tuple[SeedUser, ...] = (
    SeedUser("admin@ardee.test", "Nikhilesh", UserRole.ADMIN),
    SeedUser("ops.admin@ardee.test", "Nikhil", UserRole.ADMIN),
    SeedUser("rohan@ardee.test", "Rohan Mehta", UserRole.USER),
    SeedUser("isha@ardee.test", "Isha Kapoor", UserRole.USER),
    SeedUser("kabir@ardee.test", "Kabir Singh", UserRole.USER),
    SeedUser("ananya@ardee.test", "Ananya Rao", UserRole.USER),
    SeedUser("vivaan@ardee.test", "Vivaan Gupta", UserRole.USER),
    SeedUser("meera@ardee.test", "Meera Iyer", UserRole.USER),
)


def _resolve_password(cli_password: str | None) -> str:
    """Resolve the seed password: --password > SEED_PASSWORD env > default."""
    return cli_password or os.environ.get("SEED_PASSWORD") or DEFAULT_PASSWORD


async def seed_accounts(password: str) -> tuple[int, int]:
    """Create any missing seed accounts. Returns (created, skipped) counts."""
    password_hash = get_password_hash(password)
    created = 0
    skipped = 0

    await init_db()
    try:
        factory = get_session_factory()
        async with factory() as session:
            repository = UserRepository(session)
            for seed_user in SEED_USERS:
                existing = await repository.get_by_email(seed_user.email)
                if existing is not None:
                    skipped += 1
                    print(f"  = skip    {seed_user.role.value:<5} {seed_user.email} (exists)")
                    continue

                session.add(
                    User(
                        email=seed_user.email,
                        full_name=seed_user.full_name,
                        password_hash=password_hash,
                        role=seed_user.role,
                        is_active=True,
                    )
                )
                created += 1
                print(f"  + create  {seed_user.role.value:<5} {seed_user.email}")

            await session.commit()
    finally:
        await close_db()

    return created, skipped


async def seed_default_bot() -> bool:
    """Create a default bot (idempotent) and backfill any bot-less rows.

    Ensures documents, sessions, and usage created before bots existed become
    usable by attaching them to a single default bot. Returns True if the bot
    was created.
    """
    created = False
    await init_db()
    try:
        factory = get_session_factory()
        async with factory() as session:
            existing = (
                await session.execute(
                    select(Bot).where(
                        Bot.name == DEFAULT_BOT_NAME, Bot.deleted_at.is_(None)
                    )
                )
            ).scalar_one_or_none()

            if existing is None:
                admin = (
                    await session.execute(
                        select(User).where(User.role == UserRole.ADMIN).limit(1)
                    )
                ).scalar_one_or_none()
                existing = Bot(
                    name=DEFAULT_BOT_NAME,
                    description=DEFAULT_BOT_DESCRIPTION,
                    system_prompt=DEFAULT_BOT_SYSTEM_PROMPT,
                    created_by_id=admin.id if admin else None,
                )
                session.add(existing)
                await session.flush()
                created = True
                print(f"  + create  BOT   {DEFAULT_BOT_NAME}")
            else:
                print(f"  = skip    BOT   {DEFAULT_BOT_NAME} (exists)")

            await session.execute(
                update(RagDocument)
                .where(RagDocument.bot_id.is_(None))
                .values(bot_id=existing.id)
            )
            await session.execute(
                update(ChatSession)
                .where(ChatSession.bot_id.is_(None))
                .values(bot_id=existing.id)
            )
            await session.commit()
    finally:
        await close_db()

    return created


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Seed staging admin/user accounts.")
    parser.add_argument("--password", help="Password for all seeded accounts.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow running even when APP_ENV is not a staging/dev environment.",
    )
    args = parser.parse_args()

    setup_logging()
    settings = get_settings()
    env = settings.app_env
    print(f"Environment: {env}")

    if settings.is_production and not args.force:
        print(
            "Refusing to seed a PRODUCTION environment. "
            "Re-run with --force only if you are absolutely sure.",
            file=sys.stderr,
        )
        return 2

    password = _resolve_password(args.password)
    print(f"Seeding {len(SEED_USERS)} accounts (2 admins, 6 users)...")

    created, skipped = asyncio.run(seed_accounts(password))
    bot_created = asyncio.run(seed_default_bot())

    print("-" * 48)
    print(f"Done. Created {created}, skipped {skipped}.")
    print(f"Default bot {'created' if bot_created else 'already present'}.")
    if created:
        print(f"Shared password for new accounts: {password}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
