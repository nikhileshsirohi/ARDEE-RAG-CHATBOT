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

from app.config import get_settings
from app.core.database import _get_session_factory as get_session_factory
from app.core.database import close_db, init_db
from app.core.security import get_password_hash
from app.models.user import User, UserRole
from app.repositories.user import UserRepository

DEFAULT_PASSWORD = "StagingPass123!"


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

    print("-" * 48)
    print(f"Done. Created {created}, skipped {skipped}.")
    if created:
        print(f"Shared password for new accounts: {password}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
