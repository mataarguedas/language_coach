import { describe, expect, it, afterEach } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import PronunciationPanel from "./PronunciationPanel";
import type { ProsodyBlock, ShadowAnalysis } from "../lib/types";

afterEach(cleanup);

const PROSODY: ProsodyBlock = {
  target: { duration_s: 1.5, speaking_rate: 3.0, pause_count: 0, pause_positions_s: [] },
  learner: { duration_s: 1.5, speaking_rate: 3.0, pause_count: 0, pause_positions_s: [] },
  pace_match_score: 92,
  tips: ["Nice pace."],
};

describe("PronunciationPanel — empty state", () => {
  it("renders the 'add Azure key' message when pronunciation is null", () => {
    const analysis: ShadowAnalysis = { prosody: PROSODY, pronunciation: null };
    render(<PronunciationPanel analysis={analysis} />);

    expect(screen.getByTestId("pronunciation-empty")).toBeInTheDocument();
    expect(
      screen.getByText(/add your azure speech key and region/i),
    ).toBeInTheDocument();

    // Not an error state, and no per-word chips.
    expect(screen.queryByTestId("pronunciation-populated")).toBeNull();
    expect(screen.queryByTestId("pronunciation-error")).toBeNull();
    expect(screen.queryByRole("list")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Error state — Azure was invoked but failed. Prosody remains on the next
// step; here we show the message and reassure the user pace-match is intact.
// ---------------------------------------------------------------------------

describe("PronunciationPanel — error state", () => {
  it("renders the pronunciation_error message and reassures about pace match", () => {
    const analysis: ShadowAnalysis = {
      prosody: PROSODY,
      pronunciation: null,
      pronunciation_error: "Azure Speech API returned HTTP 500.",
    };
    render(<PronunciationPanel analysis={analysis} />);

    expect(screen.getByTestId("pronunciation-error")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText(/pronunciation unavailable/i)).toBeInTheDocument();
    expect(
      screen.getByText(/azure speech api returned http 500/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/your pace-match feedback is still available/i),
    ).toBeInTheDocument();

    // Error variant should not double up with the empty or populated ones.
    expect(screen.queryByTestId("pronunciation-empty")).toBeNull();
    expect(screen.queryByTestId("pronunciation-populated")).toBeNull();
  });

  it("does NOT render the error variant when pronunciation is null without an error", () => {
    const analysis: ShadowAnalysis = {
      prosody: PROSODY,
      pronunciation: null,
      pronunciation_error: null,
    };
    render(<PronunciationPanel analysis={analysis} />);
    expect(screen.queryByTestId("pronunciation-error")).toBeNull();
    expect(screen.getByTestId("pronunciation-empty")).toBeInTheDocument();
  });
});

describe("PronunciationPanel — populated state", () => {
  const analysis: ShadowAnalysis = {
    prosody: PROSODY,
    pronunciation: {
      overall_score: 82.4,
      words: [
        { text: "hello", accuracy_score: 95, status: "correct" },
        { text: "world", accuracy_score: 70, status: "mispronounced" },
        { text: "today", accuracy_score: 0, status: "omitted" },
        { text: "um", accuracy_score: 0, status: "inserted" },
      ],
    },
  };

  it("shows the rounded overall score and its band label", () => {
    render(<PronunciationPanel analysis={analysis} />);
    // 82.4 rounds to 82 → amber ("Close").
    expect(screen.getByLabelText(/overall pronunciation score 82 percent/i))
      .toHaveTextContent("82%");
    expect(screen.getByText(/close/i)).toBeInTheDocument();
  });

  it("renders one chip per word with status and score in the aria-label", () => {
    render(<PronunciationPanel analysis={analysis} />);
    const list = screen.getByRole("list");
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(4);

    expect(items[0]).toHaveAttribute("data-status", "correct");
    expect(items[0]).toHaveAccessibleName(/hello, correct, 95 percent/i);
    expect(items[1]).toHaveAttribute("data-status", "mispronounced");
    expect(items[2]).toHaveAttribute("data-status", "omitted");
    expect(items[3]).toHaveAttribute("data-status", "inserted");
  });

  it("applies the correct band color class to each score chip", () => {
    render(<PronunciationPanel analysis={analysis} />);
    const items = within(screen.getByRole("list")).getAllByRole("listitem");
    // correct 95 → emerald
    expect(items[0].className).toMatch(/emerald/);
    // mispronounced 70 → amber (score-band still applies)
    expect(items[1].className).toMatch(/amber/);
    // omitted → slate dashed (not colored by score)
    expect(items[2].className).toMatch(/slate/);
    expect(items[2].className).toMatch(/dashed/);
    // inserted → sky dotted
    expect(items[3].className).toMatch(/sky/);
    expect(items[3].className).toMatch(/dotted/);
  });

  it("badges omitted and inserted words with a text label", () => {
    render(<PronunciationPanel analysis={analysis} />);
    // Case-insensitive; the badges render in uppercase via CSS.
    expect(screen.getByText(/^omitted$/i)).toBeInTheDocument();
    expect(screen.getByText(/^inserted$/i)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Boundary-score bands: 64 → red, 65 → amber, 84 → amber, 85 → emerald.
// These are the exact thresholds documented in the panel's `chipClasses`; a
// silent off-by-one would flip colors and mislead learners about accuracy.
// ---------------------------------------------------------------------------

describe("PronunciationPanel — chip color band boundaries", () => {
  const makeAnalysis = (accuracy: number): ShadowAnalysis => ({
    prosody: PROSODY,
    pronunciation: {
      overall_score: accuracy,
      words: [
        { text: "w", accuracy_score: accuracy, status: "correct" },
      ],
    },
  });

  function chipClassName(accuracy: number): string {
    render(<PronunciationPanel analysis={makeAnalysis(accuracy)} />);
    return within(screen.getByRole("list"))
      .getAllByRole("listitem")[0].className;
  }

  it("64 → red band", () => {
    const cls = chipClassName(64);
    expect(cls).toMatch(/red/);
    expect(cls).not.toMatch(/amber|emerald/);
  });

  it("65 → amber band (lower boundary of amber)", () => {
    const cls = chipClassName(65);
    expect(cls).toMatch(/amber/);
    expect(cls).not.toMatch(/red|emerald/);
  });

  it("84 → amber band (upper boundary of amber)", () => {
    const cls = chipClassName(84);
    expect(cls).toMatch(/amber/);
    expect(cls).not.toMatch(/red|emerald/);
  });

  it("85 → emerald band (lower boundary of emerald)", () => {
    const cls = chipClassName(85);
    expect(cls).toMatch(/emerald/);
    expect(cls).not.toMatch(/red|amber/);
  });
});
