# =============================================================================
# Next.js frontend — production image (standalone output)
# =============================================================================
# Build context is the `frontend/` directory:
#   docker build -f docker/frontend.Dockerfile -t ardee-frontend frontend/
#
# The API base URL is inlined at BUILD time (Next.js NEXT_PUBLIC_* vars), so it
# must be passed as a build arg:
#   --build-arg NEXT_PUBLIC_API_BASE_URL=https://<backend>.onrender.com/api/v1
# On Render, set it as a service environment variable — Render forwards env vars
# to the Docker build.
# =============================================================================

# ── Stage 1: install dependencies ────────────────────────────────────────────
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci

# ── Stage 2: build ───────────────────────────────────────────────────────────
FROM node:20-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

ARG NEXT_PUBLIC_API_BASE_URL
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# ── Stage 3: runtime ─────────────────────────────────────────────────────────
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
# Next's standalone server reads PORT/HOSTNAME from the environment.
# Render injects PORT; bind all interfaces so it is reachable.
ENV HOSTNAME=0.0.0.0
ENV PORT=3000

# Non-root user
RUN addgroup -g 1001 nodejs && adduser -u 1001 -G nodejs -S nextjs

COPY --from=build /app/public ./public
COPY --from=build --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=build --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000

CMD ["node", "server.js"]
