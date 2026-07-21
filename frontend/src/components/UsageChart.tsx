"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { DailyTokenUsageMetric } from "@/lib/types";

type DayPoint = {
  key: string;
  label: string;
  tokens: number;
};

/** Monday 00:00 of the week containing `base`, shifted by `weekOffset` weeks. */
function startOfWeek(base: Date, weekOffset: number) {
  const date = new Date(base);
  date.setHours(0, 0, 0, 0);
  const dayIndex = (date.getDay() + 6) % 7; // Monday = 0
  date.setDate(date.getDate() - dayIndex + weekOffset * 7);
  return date;
}

function toLocalDateKey(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function formatTokensK(value: number) {
  return `${(value / 1000).toLocaleString(undefined, { maximumFractionDigits: 1 })}k`;
}

/** Round a max value up to a "nice" axis bound so gridlines read cleanly. */
function niceCeil(value: number) {
  if (value <= 0) {
    return 1000;
  }
  const magnitude = Math.pow(10, Math.floor(Math.log10(value)));
  const normalized = value / magnitude;
  const step = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10;
  return step * magnitude;
}

export function UsageChart({
  selectedUserId,
  version = 0,
}: {
  selectedUserId: string;
  version?: number;
}) {
  const [weekOffset, setWeekOffset] = useState(0);
  const [rows, setRows] = useState<DailyTokenUsageMetric[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const week = useMemo(() => {
    const start = startOfWeek(new Date(), weekOffset);
    const end = new Date(start);
    end.setDate(end.getDate() + 6);
    end.setHours(23, 59, 59, 999);
    return { start, end };
  }, [weekOffset]);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await api.dailyTokenUsage({
        start_at: week.start.toISOString(),
        end_at: week.end.toISOString(),
        user_id: selectedUserId === "all" ? undefined : selectedUserId,
      });
      setRows(data);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to load usage.");
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [week.start, week.end, selectedUserId]);

  useEffect(() => {
    void load();
  }, [load, version]);

  const points: DayPoint[] = useMemo(() => {
    const byDay = new Map(rows.map((row) => [row.day, row.total_tokens]));
    return Array.from({ length: 7 }, (_, index) => {
      const date = new Date(week.start);
      date.setDate(date.getDate() + index);
      const key = toLocalDateKey(date);
      return {
        key,
        label: new Intl.DateTimeFormat(undefined, { weekday: "short" }).format(date),
        tokens: byDay.get(key) ?? 0,
      };
    });
  }, [rows, week.start]);

  const weekTotal = points.reduce((sum, point) => sum + point.tokens, 0);
  const axisMax = niceCeil(Math.max(...points.map((point) => point.tokens), 0));
  const ticks = [1, 0.75, 0.5, 0.25, 0].map((fraction) => axisMax * fraction);

  const rangeLabel = `${new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
  }).format(week.start)} – ${new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
  }).format(week.end)}`;

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <button
            className="btn btn-secondary"
            onClick={() => setWeekOffset((offset) => offset - 1)}
            type="button"
          >
            ← Prev
          </button>
          <div className="min-w-40 text-center text-sm font-black text-slate-700">{rangeLabel}</div>
          <button
            className="btn btn-secondary"
            disabled={weekOffset >= 0}
            onClick={() => setWeekOffset((offset) => Math.min(0, offset + 1))}
            type="button"
          >
            Next →
          </button>
        </div>
        <div className="text-sm font-bold text-slate-500">
          Week total <span className="text-slate-900">{formatTokensK(weekTotal)}</span>
        </div>
      </div>

      {error ? (
        <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm font-semibold text-red-700">
          {error}
        </div>
      ) : (
        <div className="flex gap-3">
          <div className="flex h-56 flex-col justify-between py-1 text-right text-[11px] font-bold text-slate-400">
            {ticks.map((tick) => (
              <div key={tick}>{formatTokensK(tick)}</div>
            ))}
          </div>
          <div className="relative flex-1">
            <div className="absolute inset-0 flex flex-col justify-between py-1">
              {ticks.map((tick) => (
                <div className="border-t border-dashed border-slate-200" key={tick} />
              ))}
            </div>
            <div className="relative grid h-56 grid-cols-7 items-end gap-2 py-1">
              {points.map((point) => {
                const heightPct = axisMax > 0 ? (point.tokens / axisMax) * 100 : 0;
                return (
                  <div className="flex h-full flex-col justify-end" key={point.key}>
                    <div className="mb-1 text-center text-[11px] font-black text-slate-600">
                      {point.tokens > 0 ? formatTokensK(point.tokens) : ""}
                    </div>
                    <div
                      className="admin-bar"
                      style={{ height: `${point.tokens > 0 ? Math.max(heightPct, 2) : 0}%` }}
                      title={`${point.label}: ${point.tokens.toLocaleString()} tokens`}
                    />
                  </div>
                );
              })}
            </div>
            <div className="grid grid-cols-7 gap-2 pt-2">
              {points.map((point) => (
                <div className="text-center text-xs font-bold text-slate-500" key={point.key}>
                  {point.label}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
      {loading ? <div className="mt-2 text-xs font-semibold text-slate-400">Loading…</div> : null}
    </div>
  );
}
