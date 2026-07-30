import { useEffect, useRef, useState, type RefObject } from "react";
import type { TimingSchedule } from "./types";

/**
 * Binary-search the contiguous, ordered entries for the one active at `ms`.
 * Returns -1 if `ms` falls outside every entry (before start, after end,
 * or in a gap — though the backend produces gap-free schedules).
 *
 * Pure function; exported for unit-testing without React.
 */
export function findActiveIndex(
  entries: TimingSchedule["entries"],
  ms: number,
): number {
  let lo = 0;
  let hi = entries.length - 1;
  while (lo <= hi) {
    const mid = (lo + hi) >>> 1;
    const e = entries[mid];
    if (ms < e.start_ms) {
      hi = mid - 1;
    } else if (ms >= e.end_ms) {
      lo = mid + 1;
    } else {
      return mid;
    }
  }
  return -1;
}

/**
 * Consumes a backend TimingSchedule and drives active-word index from the
 * audio element's `timeupdate` / `currentTime`.
 *
 * Never recomputes or modifies the schedule — it only reads what the backend
 * produced.  Language-blind: works identically for zh, es, and en.
 *
 * Returns the 0-based index of the currently active TimingEntry, or -1 when
 * playback is outside all entries (before the clip starts, after it ends, or
 * paused at a boundary).
 */
export function useScheduler(
  schedule: TimingSchedule,
  audioRef: RefObject<HTMLAudioElement | null>,
): number {
  const [activeIndex, setActiveIndex] = useState(-1);

  // Keep a ref so the timeupdate handler always reads the latest schedule
  // without needing to re-register the listener on every render.
  const scheduleRef = useRef(schedule);
  scheduleRef.current = schedule;

  // Reset when the schedule changes (new synthesis loaded).
  useEffect(() => {
    setActiveIndex(-1);
  }, [schedule]);

  // Attach / detach the timeupdate listener.
  // audioRef is a stable object — this effect runs once after mount.
  useEffect(() => {
    const el = audioRef.current;
    if (!el) return;

    function onTimeUpdate() {
      const ms = el!.currentTime * 1000;
      setActiveIndex(findActiveIndex(scheduleRef.current.entries, ms));
    }

    el.addEventListener("timeupdate", onTimeUpdate);
    return () => el.removeEventListener("timeupdate", onTimeUpdate);
  }, [audioRef]);

  return activeIndex;
}
