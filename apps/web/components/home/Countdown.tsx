"use client";
import { useEffect, useState } from "react";

/** Counts down to the next local midnight. Renders a stable placeholder on the
 *  server to avoid hydration mismatch, then ticks on the client. */
export function Countdown() {
  const [left, setLeft] = useState<number | null>(null);

  useEffect(() => {
    const end = new Date();
    end.setHours(24, 0, 0, 0);
    const tick = () => setLeft(Math.max(0, end.getTime() - Date.now()));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  const parts = format(left);
  return (
    <div className="flex items-center gap-1.5">
      <span className="hidden text-xs font-semibold text-white/90 sm:inline">Kết thúc sau</span>
      {parts.map((value, i) => (
        <span
          key={i}
          className="grid h-7 min-w-7 place-items-center rounded-md bg-black/25 px-1 font-mono text-sm font-bold tabular-nums text-white"
        >
          {value}
        </span>
      ))}
    </div>
  );
}

function format(ms: number | null): string[] {
  if (ms === null) return ["--", "--", "--"];
  const total = Math.floor(ms / 1000);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  return [h, m, s].map((n) => String(n).padStart(2, "0"));
}
