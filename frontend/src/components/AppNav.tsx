"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { clearTokens } from "@/lib/auth";
import type { SessionUser } from "@/lib/types";

function navClass(active: boolean) {
  return `rounded-lg px-3 py-2 text-sm font-bold transition ${
    active ? "bg-[#dcecf2] text-[#0f5269]" : "text-slate-600 hover:bg-slate-100"
  }`;
}

export function AppNav({ user }: { user: SessionUser }) {
  const pathname = usePathname();
  const router = useRouter();

  function logout() {
    clearTokens();
    router.replace("/login");
  }

  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-7xl flex-col gap-3 px-4 py-4 sm:flex-row sm:items-center sm:justify-between lg:px-6">
        <div className="flex items-center gap-3">
          <Link href="/dashboard" className="text-lg font-black text-slate-950">
            Ardee RAG
          </Link>
          <div className="flex items-center gap-2">
            <span
              aria-hidden
              className="grid h-9 w-9 place-items-center rounded-full bg-[#dcecf2] text-sm font-black text-[#0f5269]"
            >
              {(user.full_name?.trim() || user.email).slice(0, 1).toUpperCase()}
            </span>
            <div className="leading-tight">
              <div className="text-sm font-black text-slate-900">
                {user.full_name?.trim() || "Unnamed user"}
              </div>
              <div className="text-xs font-semibold text-slate-500">{user.email}</div>
            </div>
          </div>
        </div>
        <nav className="flex flex-wrap items-center gap-2">
          <Link className={navClass(pathname === "/dashboard")} href="/dashboard">
            Chat
          </Link>
          {user.role === "ADMIN" ? (
            <Link className={navClass(pathname.startsWith("/admin"))} href="/admin">
              Admin Console
            </Link>
          ) : null}
          <span className="badge">{user.role}</span>
          <button className="btn btn-secondary" onClick={logout} type="button">
            Logout
          </button>
        </nav>
      </div>
    </header>
  );
}
