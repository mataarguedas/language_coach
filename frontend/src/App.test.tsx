/**
 * App-level slider tests.
 *
 * Drives the whole flow (Keys → … → Playback+Record → Pronunciation → Pace
 * match) through userEvent, with heavy children (Recorder, KaraokePlayer)
 * and network calls (lib/api) stubbed. Verifies:
 *
 *   * After a successful analyze with pronunciation populated: slider is on
 *     step 6 and PronunciationPanel's populated variant is on screen.
 *   * After a successful analyze with pronunciation null: PronunciationPanel
 *     renders its empty state; Continue still advances to Pace match (step 7).
 *   * Restart on the Pace-match panel resets to step 0 and clears both blocks.
 *
 * Every panel is always mounted (the slider translates horizontally rather
 * than conditionally rendering), so "current step" is asserted via the
 * shared step-indicator text `{step+1} / {TOTAL_STEPS}` and via which
 * PronunciationPanel variant is currently in the DOM.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent, { type UserEvent } from "@testing-library/user-event";

// ---------------------------------------------------------------------------
// Mocks — hoisted by vitest before App is imported below.
// ---------------------------------------------------------------------------

vi.mock("./components/Recorder", () => ({
  default: ({
    onSubmit,
    submitting,
  }: {
    onSubmit: (b: Blob, m: string | null) => void;
    submitting?: boolean;
  }) => (
    <button
      type="button"
      data-testid="mock-recorder-submit"
      disabled={submitting}
      onClick={() =>
        onSubmit(new Blob(["fake-audio"], { type: "audio/webm" }), "audio/webm")
      }
    >
      submit-recording
    </button>
  ),
}));

vi.mock("./components/KaraokePlayer", () => ({
  default: () => <div data-testid="mock-karaoke" />,
}));

vi.mock("./lib/api", () => ({
  fetchLanguages: vi.fn(),
  fetchVoices: vi.fn(),
  synthesize: vi.fn(),
  analyzeShadow: vi.fn(),
}));

vi.mock("./lib/keys", () => ({
  getFishKey: vi.fn(() => "test-fish-key"),
  getOpenAiKey: vi.fn(() => ""),
  getAzureKey: vi.fn(() => ""),
  getAzureRegion: vi.fn(() => ""),
  setFishKey: vi.fn(),
  setOpenAiKey: vi.fn(),
  setAzureKey: vi.fn(),
  setAzureRegion: vi.fn(),
  clearKeys: vi.fn(),
}));

import App from "./App";
import * as api from "./lib/api";
import type { ShadowAnalysis } from "./lib/types";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function panelSection(title: string | RegExp): HTMLElement {
  const h1 = screen.getByRole("heading", { level: 1, name: title });
  const section = h1.closest("section");
  if (!section) throw new Error(`No <section> for panel titled ${String(title)}`);
  return section as HTMLElement;
}

async function clickInPanel(
  user: UserEvent,
  title: string | RegExp,
  buttonName: RegExp,
) {
  const btn = within(panelSection(title)).getByRole("button", {
    name: buttonName,
  });
  await user.click(btn);
}

/** Assert the slider is currently showing step N (0-indexed). */
function expectStep(n: number) {
  // Every NavBar shares state, so every step indicator reads "N+1 / 8" —
  // presence is sufficient and asserts the parent state directly.
  expect(screen.getAllByText(`${n + 1} / 8`).length).toBeGreaterThan(0);
}

async function walkFromKeysToRecordStep(user: UserEvent) {
  // 0 Keys → 1 Language → 2 Voice → 3 Speed → 4 Text
  await clickInPanel(user, /^api keys$/i, /continue/i);
  await clickInPanel(user, /^choose a language$/i, /continue/i);
  await waitFor(() => {
    // Wait for voices to load before we try to advance past Voice step.
    const voiceSection = panelSection(/^pick a voice$/i);
    const btn = within(voiceSection).getByRole("button", { name: /continue/i });
    expect(btn).not.toBeDisabled();
  });
  await clickInPanel(user, /^pick a voice$/i, /continue/i);
  await clickInPanel(user, /^set the speed$/i, /continue/i);

  const textSection = panelSection(/^enter the text$/i);
  const textarea = within(textSection).getByRole("textbox");
  await user.type(textarea, "hello world");
  await clickInPanel(user, /^enter the text$/i, /synthesize/i);

  // After synth resolves, App auto-advances to step 5 (Playback+Record).
  await waitFor(() => expectStep(5));
}

const PROSODY_FIXTURE = {
  target: { duration_s: 1.5, speaking_rate: 3, pause_count: 0, pause_positions_s: [] },
  learner: { duration_s: 1.5, speaking_rate: 3, pause_count: 0, pause_positions_s: [] },
  pace_match_score: 92,
  tips: ["Nice pace."],
};

// ---------------------------------------------------------------------------
// Setup / teardown
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.clearAllMocks();

  (api.fetchLanguages as ReturnType<typeof vi.fn>).mockResolvedValue([
    { code: "en", label: "English" },
    { code: "es", label: "Spanish" },
    { code: "zh", label: "Mandarin" },
  ]);
  (api.fetchVoices as ReturnType<typeof vi.fn>).mockResolvedValue([
    { reference_id: "v1", label: "Voice One", language: "en", sample_url: null },
  ]);
  (api.synthesize as ReturnType<typeof vi.fn>).mockResolvedValue({
    language: "en",
    voice_id: "v1",
    speed: 1.0,
    cache_key: "cache-abc",
    audio_url: "/api/synthesize/audio/cache-abc",
    timing: { total_ms: 1200, entries: [] },
  });
});

afterEach(() => {
  cleanup();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("App slider — analyze with pronunciation populated", () => {
  it("advances to step 6 and shows the populated PronunciationPanel", async () => {
    const analysis: ShadowAnalysis = {
      prosody: PROSODY_FIXTURE,
      pronunciation: {
        overall_score: 87,
        words: [
          { text: "hello", accuracy_score: 95, status: "correct" },
          { text: "world", accuracy_score: 80, status: "mispronounced" },
        ],
      },
    };
    (api.analyzeShadow as ReturnType<typeof vi.fn>).mockResolvedValue(analysis);

    const user = userEvent.setup();
    render(<App />);
    await walkFromKeysToRecordStep(user);

    // Trigger the mocked recorder's submit → App calls analyzeShadow → advances.
    await user.click(screen.getByTestId("mock-recorder-submit"));

    await waitFor(() => expectStep(6));
    // Populated variant is visible; empty variant is not mounted at all.
    expect(screen.getByTestId("pronunciation-populated")).toBeInTheDocument();
    expect(screen.queryByTestId("pronunciation-empty")).toBeNull();

    // Sanity: one round-trip only.
    expect(api.analyzeShadow).toHaveBeenCalledTimes(1);
  });
});

describe("App slider — analyze with pronunciation null", () => {
  it("advances to step 6 with the empty PronunciationPanel and Continue reaches Pace match", async () => {
    const analysis: ShadowAnalysis = {
      prosody: PROSODY_FIXTURE,
      pronunciation: null,
    };
    (api.analyzeShadow as ReturnType<typeof vi.fn>).mockResolvedValue(analysis);

    const user = userEvent.setup();
    render(<App />);
    await walkFromKeysToRecordStep(user);
    await user.click(screen.getByTestId("mock-recorder-submit"));

    await waitFor(() => expectStep(6));
    // Empty variant is visible.
    expect(screen.getByTestId("pronunciation-empty")).toBeInTheDocument();
    expect(
      screen.getByText(/add your azure speech key and region/i),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("pronunciation-populated")).toBeNull();

    // Continue from the Pronunciation panel → advances to Pace match (step 7).
    await clickInPanel(user, /^pronunciation$/i, /continue/i);
    await waitFor(() => expectStep(7));
    // Pace match panel content is now visible; FeedbackPanel renders the tips list.
    expect(
      within(panelSection(/^pace match$/i)).getByText(/nice pace/i),
    ).toBeInTheDocument();
  });
});

describe("App slider — Restart", () => {
  it("resets to step 0 and clears both analysis blocks", async () => {
    const analysis: ShadowAnalysis = {
      prosody: PROSODY_FIXTURE,
      pronunciation: {
        overall_score: 87,
        words: [{ text: "hello", accuracy_score: 95, status: "correct" }],
      },
    };
    (api.analyzeShadow as ReturnType<typeof vi.fn>).mockResolvedValue(analysis);

    const user = userEvent.setup();
    render(<App />);
    await walkFromKeysToRecordStep(user);
    await user.click(screen.getByTestId("mock-recorder-submit"));
    await waitFor(() => expectStep(6));

    // Advance to Pace match, then click Start over.
    await clickInPanel(user, /^pronunciation$/i, /continue/i);
    await waitFor(() => expectStep(7));
    await clickInPanel(user, /^pace match$/i, /start over/i);

    // Back to step 0.
    await waitFor(() => expectStep(0));

    // Both analysis blocks cleared: `analysis` is null, so App renders the
    // "No analysis yet" placeholder inside both the Pronunciation and
    // Pace-match panels (PronunciationPanel itself isn't mounted at this
    // point — it only renders once an analyze response arrives).
    expect(screen.queryByTestId("pronunciation-populated")).toBeNull();
    expect(screen.queryByTestId("pronunciation-empty")).toBeNull();

    const pronSection = panelSection(/^pronunciation$/i);
    expect(within(pronSection).getByText(/no analysis yet/i)).toBeInTheDocument();

    const paceSection = panelSection(/^pace match$/i);
    expect(within(paceSection).getByText(/no analysis yet/i)).toBeInTheDocument();
  });
});
