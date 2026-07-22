"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { getStoredUser } from "@/lib/auth";
import type { SessionUser, UserRole } from "@/lib/types";

export function ProtectedRoute({
  children,
  role,
}: {
  children: (user: SessionUser) => React.ReactNode;
  role?: UserRole;
}) {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const user = useMemo(() => getStoredUser(), []);

  useEffect(() => {
    if (!user) {
      router.replace("/login");
      return;
    }
    if (role && user.role !== role) {
      router.replace("/bots");
      return;
    }
    setReady(true);
  }, [role, router, user]);

  if (!ready || !user) {
    return (
      <main className="grid min-h-screen place-items-center px-4">
        <div className="panel px-5 py-4 text-sm font-semibold text-slate-600">Loading dashboard...</div>
      </main>
    );
  }

  return <>{children(user)}</>;
}
