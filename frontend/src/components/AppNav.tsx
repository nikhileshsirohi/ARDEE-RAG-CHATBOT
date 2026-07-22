"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { clearTokens } from "@/lib/auth";
import type { SessionUser } from "@/lib/types";

function navClass(active: boolean) {
  return `rounded-lg px-3 py-2 text-sm font-semibold transition ${
    active
      ? "bg-[var(--primary-soft)] text-[var(--primary-strong)] shadow-sm"
      : "text-slate-600 hover:bg-white/70 hover:text-slate-900"
  }`;
}

export function AppNav({ user }: { user: SessionUser }) {
  const pathname = usePathname();
  const router = useRouter();
  const isAdmin = user.role === "ADMIN";

  function logout() {
    clearTokens();
    router.replace("/login");
  }

  return (
    <header className="sticky top-0 z-40 border-b border-[var(--line)] bg-white/70 backdrop-blur-xl">
      <div className="mx-auto flex max-w-7xl flex-col gap-3 px-4 py-3.5 sm:flex-row sm:items-center sm:justify-between lg:px-6">
        <div className="flex items-center gap-4">
          <Link href="/bots" className="brand-mark text-[1.35rem] text-[var(--foreground)]">
            Ardee<span className="text-[var(--primary)]">.</span>
          </Link>
          <div className="hidden h-7 w-px bg-[var(--line-strong)] sm:block" aria-hidden />
          <div className="flex items-center gap-2.5">
            <span
              aria-hidden
              className="grid h-9 w-9 place-items-center rounded-full bg-gradient-to-br from-[var(--primary-soft)] to-[#d5e8ef] text-sm font-bold text-[var(--primary-strong)] ring-1 ring-[var(--primary-soft-border)]"
            >
              {(user.full_name?.trim() || user.email).slice(0, 1).toUpperCase()}
            </span>
            <div className="leading-tight">
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold text-slate-900">
                  {user.full_name?.trim() || "Unnamed user"}
                </span>
                {isAdmin ? (
                  <span className="text-[0.65rem] font-semibold uppercase tracking-[0.08em] text-[var(--primary)]">
                    Admin
                  </span>
                ) : null}
              </div>
              <div className="text-xs font-medium text-slate-500">{user.email}</div>
            </div>
          </div>
        </div>
        <nav className="flex flex-wrap items-center gap-1.5">
          <Link className={navClass(pathname === "/bots" || pathname.startsWith("/bots/"))} href="/bots">
            Bots
          </Link>
          <Link className={navClass(pathname === "/usage")} href="/usage">
            My usage
          </Link>
          {isAdmin ? (
            <Link className={navClass(pathname.startsWith("/admin"))} href="/admin">
              Console
            </Link>
          ) : null}
          <button className="btn btn-secondary ml-1" onClick={logout} type="button">
            Logout
          </button>
        </nav>
      </div>
    </header>
  );
}
