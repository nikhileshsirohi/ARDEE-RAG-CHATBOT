import type { SessionUser, TokenResponse } from "@/lib/types";

const ACCESS_TOKEN_KEY = "ardee.accessToken";
const REFRESH_TOKEN_KEY = "ardee.refreshToken";
const EXPIRES_AT_KEY = "ardee.expiresAt";

type JwtPayload = {
  sub: string;
  email: string;
  full_name?: string | null;
  role: string;
  exp: number;
};

function decodeBase64Url(value: string) {
  const base64 = value.replace(/-/g, "+").replace(/_/g, "/");
  const padded = base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), "=");
  return atob(padded);
}

export function decodeUserFromToken(token: string): SessionUser | null {
  try {
    const [, payload] = token.split(".");
    if (!payload) {
      return null;
    }
    const decoded = JSON.parse(decodeBase64Url(payload)) as JwtPayload;
    return {
      id: decoded.sub,
      email: decoded.email,
      full_name: decoded.full_name ?? null,
      role: decoded.role.toUpperCase() === "ADMIN" ? "ADMIN" : "USER",
    };
  } catch {
    return null;
  }
}

export function persistTokens(tokens: TokenResponse) {
  if (typeof window === "undefined") {
    return;
  }
  localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access_token);
  localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);
  localStorage.setItem(EXPIRES_AT_KEY, String(Date.now() + tokens.expires_in * 1000));
}

export function clearTokens() {
  if (typeof window === "undefined") {
    return;
  }
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
  localStorage.removeItem(EXPIRES_AT_KEY);
}

export function getAccessToken() {
  if (typeof window === "undefined") {
    return null;
  }
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function getRefreshToken() {
  if (typeof window === "undefined") {
    return null;
  }
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

export function getStoredUser() {
  const token = getAccessToken();
  return token ? decodeUserFromToken(token) : null;
}
