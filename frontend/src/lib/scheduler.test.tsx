import { describe, it, expect, afterEach } from "vitest";
import { render, act, cleanup } from "@testing-library/react";
import { useRef } from "react";
import { findActiveIndex, useScheduler } from "./scheduler";
import type { TimingSchedule } from "./types";

afterEach(cleanup);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const SCHEDULE: TimingSchedule = {
  total_ms: 3000,
  entries: [
    { token: { text: "Hello", index: 0, start: 0, end: 5 }, start_ms: 0, end_ms: 1000 },
    { token: { text: "world", index: 1, start: 6, end: 11 }, start_ms: 1000, end_ms: 2000 },
    { token: { text: ".", index: 2, start: 11, end: 12 }, start_ms: 2000, end_ms: 3000 },
  ],
};

/** Renders the hook with an external audio element; returns helpers. */
function renderScheduler(schedule: TimingSchedule) {
  const audioEl = document.createElement("audio");
  // jsdom's HTMLMediaElement does not implement currentTime natively.
  let _currentTime = 0;
  Object.defineProperty(audioEl, "currentTime", {
    get: () => _currentTime,
    set: (v: number) => { _currentTime = v; },
    configurable: true,
  });

  function Harness() {
    const audioRef = useRef<HTMLAudioElement>(audioEl);
    const idx = useScheduler(schedule, audioRef);
    return <span data-testid="idx">{idx}</span>;
  }

  const { getByTestId } = render(<Harness />);

  function fireTimeUpdate(currentTime: number) {
    act(() => {
      audioEl.currentTime = currentTime;
      audioEl.dispatchEvent(new Event("timeupdate"));
    });
  }

  return { getByTestId, fireTimeUpdate };
}

// ---------------------------------------------------------------------------
// findActiveIndex — pure function, no React
// ---------------------------------------------------------------------------

describe("findActiveIndex", () => {
  const { entries } = SCHEDULE;

  it("returns -1 for empty entries", () => {
    expect(findActiveIndex([], 100)).toBe(-1);
  });

  it("returns -1 before the first entry", () => {
    expect(findActiveIndex(entries, -1)).toBe(-1);
  });

  it("returns 0 at t=0 (inclusive start)", () => {
    expect(findActiveIndex(entries, 0)).toBe(0);
  });

  it("returns 0 within the first entry", () => {
    expect(findActiveIndex(entries, 500)).toBe(0);
    expect(findActiveIndex(entries, 999)).toBe(0);
  });

  it("returns 1 at the exact boundary where first ends and second starts", () => {
    expect(findActiveIndex(entries, 1000)).toBe(1);
  });

  it("returns 1 within the second entry", () => {
    expect(findActiveIndex(entries, 1500)).toBe(1);
    expect(findActiveIndex(entries, 1999)).toBe(1);
  });

  it("returns 2 within the third entry", () => {
    expect(findActiveIndex(entries, 2000)).toBe(2);
    expect(findActiveIndex(entries, 2999)).toBe(2);
  });

  it("returns -1 at total_ms (past the last entry's end_ms)", () => {
    expect(findActiveIndex(entries, 3000)).toBe(-1);
  });

  it("returns -1 well past the end", () => {
    expect(findActiveIndex(entries, 99999)).toBe(-1);
  });
});

// ---------------------------------------------------------------------------
// useScheduler hook — wired to timeupdate events
// ---------------------------------------------------------------------------

describe("useScheduler", () => {
  it("starts at -1 before any timeupdate", () => {
    const { getByTestId } = renderScheduler(SCHEDULE);
    expect(getByTestId("idx").textContent).toBe("-1");
  });

  it("returns correct index when timeupdate fires at 0.5s (first entry)", () => {
    const { getByTestId, fireTimeUpdate } = renderScheduler(SCHEDULE);
    fireTimeUpdate(0.5);
    expect(getByTestId("idx").textContent).toBe("0");
  });

  it("advances to index 1 when currentTime moves into second entry", () => {
    const { getByTestId, fireTimeUpdate } = renderScheduler(SCHEDULE);
    fireTimeUpdate(0.5);
    fireTimeUpdate(1.5);
    expect(getByTestId("idx").textContent).toBe("1");
  });

  it("returns -1 once playback passes the last entry", () => {
    const { getByTestId, fireTimeUpdate } = renderScheduler(SCHEDULE);
    fireTimeUpdate(2.5);
    fireTimeUpdate(3.0); // past end
    expect(getByTestId("idx").textContent).toBe("-1");
  });

  it("is language-blind: same timing logic for zh tokens", () => {
    const zhSchedule: TimingSchedule = {
      total_ms: 2000,
      entries: [
        { token: { text: "你好", index: 0, start: 0, end: 2 }, start_ms: 0, end_ms: 1000 },
        { token: { text: "世界", index: 1, start: 2, end: 4 }, start_ms: 1000, end_ms: 2000 },
      ],
    };
    const { getByTestId, fireTimeUpdate } = renderScheduler(zhSchedule);
    fireTimeUpdate(0.4);
    expect(getByTestId("idx").textContent).toBe("0");
    fireTimeUpdate(1.2);
    expect(getByTestId("idx").textContent).toBe("1");
  });

  it("resets to -1 on timeupdate before first token even after previous match", () => {
    const { getByTestId, fireTimeUpdate } = renderScheduler(SCHEDULE);
    fireTimeUpdate(0.5);
    expect(getByTestId("idx").textContent).toBe("0");
    // Simulate a seek back before the clip
    fireTimeUpdate(-0.1);
    expect(getByTestId("idx").textContent).toBe("-1");
  });
});
