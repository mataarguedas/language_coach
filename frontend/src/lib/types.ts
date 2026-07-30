export type Language = "zh" | "es" | "en";

export interface LanguageMeta {
  code: Language;
  label: string;
}

export interface Voice {
  reference_id: string;
  label: string;
  language: Language;
  sample_url: string | null;
}

export interface SpeedPreset {
  value: number;
  label: string;
}

export const SPEED_PRESETS: SpeedPreset[] = [
  { value: 0.7, label: "0.7× Slow" },
  { value: 0.85, label: "0.85×" },
  { value: 1.0, label: "1.0× Normal" },
  { value: 1.15, label: "1.15× Fast" },
];

export const MAX_TEXT_CHARS = 500;

export interface TimingEntry {
  token: { text: string; index: number; start: number; end: number };
  start_ms: number;
  end_ms: number;
}

export interface TimingSchedule {
  total_ms: number;
  entries: TimingEntry[];
}

export interface SynthesizeRequest {
  text: string;
  language: Language;
  voice_id: string;
  speed: number;
}

export interface SynthesizeResponse {
  language: Language;
  voice_id: string;
  speed: number;
  cache_key: string;
  audio_url: string;
  timing: TimingSchedule;
}

export interface ProsodyFeatures {
  duration_s: number;
  speaking_rate: number;
  pause_count: number;
  pause_positions_s: number[];
}

export interface ProsodyBlock {
  target: ProsodyFeatures;
  learner: ProsodyFeatures;
  pace_match_score: number;
  tips: string[];
}

export type PronunciationStatus =
  | "correct"
  | "mispronounced"
  | "omitted"
  | "inserted";

export interface PronunciationWord {
  text: string;
  accuracy_score: number;
  status: PronunciationStatus;
}

export interface PronunciationResult {
  overall_score: number;
  words: PronunciationWord[];
}

export interface ShadowAnalysis {
  prosody: ProsodyBlock;
  pronunciation: PronunciationResult | null;
  // Populated when Azure was invoked but failed (bad key, transient 5xx,
  // malformed response). Prosody is still populated in that case — Azure
  // failure never fails the whole request. See CLAUDE.md "Independence".
  pronunciation_error?: string | null;
}

export const MAX_RECORDING_MS = 30_000;
