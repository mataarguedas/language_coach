import { useCallback, useEffect, useState, type ReactNode } from "react";
import FeedbackPanel from "./components/FeedbackPanel";
import KaraokePlayer from "./components/KaraokePlayer";
import KeyEntry from "./components/KeyEntry";
import LanguagePicker from "./components/LanguagePicker";
import PronunciationPanel from "./components/PronunciationPanel";
import Recorder from "./components/Recorder";
import SpeedControl from "./components/SpeedControl";
import VoicePicker from "./components/VoicePicker";
import { analyzeShadow, fetchLanguages, fetchVoices, synthesize } from "./lib/api";
import { getAzureKey, getAzureRegion, getFishKey, getOpenAiKey } from "./lib/keys";
import type {
  Language,
  LanguageMeta,
  ShadowAnalysis,
  TimingSchedule,
  Voice,
} from "./lib/types";
import { MAX_TEXT_CHARS } from "./lib/types";

const DEFAULT_LANGUAGE: Language = "en";
const DEFAULT_SPEED = 1.0;
const TOTAL_STEPS = 8;

export default function App() {
  const [step, setStep] = useState(0);

  const [languages, setLanguages] = useState<LanguageMeta[]>([]);
  const [language, setLanguage] = useState<Language>(DEFAULT_LANGUAGE);

  const [voices, setVoices] = useState<Voice[]>([]);
  const [voicesLoading, setVoicesLoading] = useState(false);
  const [voiceId, setVoiceId] = useState("");

  const [speed, setSpeed] = useState(DEFAULT_SPEED);
  const [text, setText] = useState("");

  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [timing, setTiming] = useState<TimingSchedule | null>(null);
  const [cacheKey, setCacheKey] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [analysis, setAnalysis] = useState<ShadowAnalysis | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [analyzeError, setAnalyzeError] = useState<string | null>(null);

  const [, setKeyRevision] = useState(0);
  const bumpKeys = useCallback(() => setKeyRevision((n) => n + 1), []);

  const apiBase = import.meta.env.VITE_API_URL ?? "";

  useEffect(() => {
    fetchLanguages()
      .then(setLanguages)
      .catch(() => {
        setLanguages([
          { code: "zh", label: "Mandarin" },
          { code: "es", label: "Spanish" },
          { code: "en", label: "English" },
        ]);
      });
  }, []);

  useEffect(() => {
    setVoicesLoading(true);
    setVoiceId("");
    setAudioUrl(null);
    setTiming(null);
    setCacheKey(null);
    setAnalysis(null);
    setAnalyzeError(null);
    fetchVoices(language)
      .then((vs) => {
        setVoices(vs);
        if (vs.length > 0) setVoiceId(vs[0].reference_id);
      })
      .catch(() => setVoices([]))
      .finally(() => setVoicesLoading(false));
  }, [language]);

  async function handleSynthesize() {
    const fishKey = getFishKey();
    const openAiKey = getOpenAiKey();
    if (!fishKey) {
      setError("Please enter your Fish Audio API key on the first step.");
      return;
    }
    if (language === "zh" && !openAiKey) {
      setError(
        "Mandarin karaoke needs an OpenAI key for word segmentation. Go back to the API Keys step.",
      );
      return;
    }
    if (!voiceId) {
      setError("Please select a voice.");
      return;
    }
    if (!text.trim()) {
      setError("Please enter some text.");
      return;
    }
    if (text.length > MAX_TEXT_CHARS) {
      setError(`Text is ${text.length} characters; the limit is ${MAX_TEXT_CHARS}.`);
      return;
    }

    setError(null);
    setSyncing(true);
    try {
      const result = await synthesize(
        { text: text.trim(), language, voice_id: voiceId, speed },
        fishKey,
        openAiKey,
      );
      setAudioUrl(`${apiBase}${result.audio_url}`);
      setTiming(result.timing);
      setCacheKey(result.cache_key);
      setAnalysis(null);
      setAnalyzeError(null);
      setStep(5);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Synthesis failed.");
    } finally {
      setSyncing(false);
    }
  }

  async function handleAnalyze(blob: Blob, mimeType: string | null) {
    if (!cacheKey) return;
    setAnalyzeError(null);
    setAnalyzing(true);
    try {
      const ext = mimeType && mimeType.includes("ogg") ? "ogg" : "webm";
      // Single round-trip: backend returns { prosody, pronunciation | null }.
      // Azure creds are only sent when both are present — otherwise the backend
      // returns pronunciation: null and PronunciationPanel renders its empty state.
      const azureKey = getAzureKey();
      const azureRegion = getAzureRegion();
      const azure =
        azureKey && azureRegion ? { key: azureKey, region: azureRegion } : undefined;
      const result = await analyzeShadow({
        learner: blob,
        learnerFilename: `learner.${ext}`,
        targetCacheKey: cacheKey,
        targetText: text.trim(),
        language,
        azure,
      });
      setAnalysis(result);
      // Advance to the pronunciation panel (step 6); the user clicks Continue
      // from there to reach the pace-match panel (step 7).
      setStep(6);
    } catch (err) {
      setAnalyzeError(err instanceof Error ? err.message : "Analysis failed.");
    } finally {
      setAnalyzing(false);
    }
  }

  const charsLeft = MAX_TEXT_CHARS - text.length;
  const overLimit = text.length > MAX_TEXT_CHARS;

  const hasFishKey = !!getFishKey();
  const hasOpenAiKey = !!getOpenAiKey();
  const keysReady = hasFishKey && (language !== "zh" || hasOpenAiKey);

  const languagesForPicker =
    languages.length > 0
      ? languages
      : [
          { code: "zh" as Language, label: "Mandarin" },
          { code: "es" as Language, label: "Spanish" },
          { code: "en" as Language, label: "English" },
        ];

  const goNext = () => setStep((s) => Math.min(s + 1, TOTAL_STEPS - 1));
  const goBack = () => setStep((s) => Math.max(s - 1, 0));
  const restart = () => {
    setStep(0);
    setText("");
    setAudioUrl(null);
    setTiming(null);
    setCacheKey(null);
    setAnalysis(null);
    setAnalyzeError(null);
    setError(null);
  };

  return (
    <div className="h-screen w-screen overflow-hidden bg-slate-50 text-slate-900">
      <div
        className="flex h-full transition-transform duration-500 ease-out"
        style={{ width: `${TOTAL_STEPS * 100}vw`, transform: `translateX(-${step * (100 / TOTAL_STEPS)}%)` }}
      >
        <Panel title="API Keys" subtitle="Bring your own keys. Nothing is stored server-side.">
          <div className="w-full max-w-lg">
            <KeyEntry language={language} onChange={bumpKeys} />
          </div>
          <NavBar
            step={step}
            onBack={goBack}
            onNext={goNext}
            nextDisabled={!hasFishKey}
            nextLabel="Continue"
          />
        </Panel>

        <Panel title="Choose a language" subtitle="Everything downstream is scoped to this language.">
          <div className="w-full max-w-lg">
            <LanguagePicker
              languages={languagesForPicker}
              value={language}
              onChange={(l) => {
                setLanguage(l);
                setError(null);
              }}
            />
            {language === "zh" && !hasOpenAiKey && (
              <p className="mt-4 rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-700">
                Mandarin needs an OpenAI key. Go back and add one before continuing.
              </p>
            )}
          </div>
          <NavBar
            step={step}
            onBack={goBack}
            onNext={goNext}
            nextDisabled={!keysReady}
            nextLabel="Continue"
          />
        </Panel>

        <Panel title="Pick a voice" subtitle="Only voices for the selected language are shown.">
          <div className="w-full max-w-lg">
            <VoicePicker
              voices={voices}
              value={voiceId}
              onChange={setVoiceId}
              loading={voicesLoading}
            />
          </div>
          <NavBar
            step={step}
            onBack={goBack}
            onNext={goNext}
            nextDisabled={!voiceId}
            nextLabel="Continue"
          />
        </Panel>

        <Panel title="Set the speed" subtitle="Native prosody presets from Fish Audio.">
          <div className="w-full max-w-lg">
            <SpeedControl value={speed} onChange={setSpeed} />
          </div>
          <NavBar step={step} onBack={goBack} onNext={goNext} nextLabel="Continue" />
        </Panel>

        <Panel title="Enter the text" subtitle="Up to 500 characters per synthesis.">
          <div className="w-full max-w-2xl space-y-3">
            <div className="flex items-baseline justify-between">
              <label htmlFor="text-input" className="text-xs font-medium text-slate-600">
                Text
              </label>
              <span
                className={[
                  "text-xs",
                  overLimit ? "font-medium text-red-500" : "text-slate-400",
                ].join(" ")}
              >
                {charsLeft} chars left
              </span>
            </div>
            <textarea
              id="text-input"
              rows={8}
              value={text}
              onChange={(e) => {
                setText(e.target.value);
                setError(null);
              }}
              placeholder={
                language === "zh"
                  ? "输入文本…"
                  : language === "es"
                  ? "Escriba el texto…"
                  : "Type or paste text…"
              }
              className={[
                "w-full resize-none rounded-md border px-3 py-2 text-base focus:outline-none focus:ring-1",
                overLimit
                  ? "border-red-400 focus:border-red-500 focus:ring-red-500"
                  : "border-slate-300 focus:border-slate-500 focus:ring-slate-500",
              ].join(" ")}
            />
            {error && (
              <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-600">{error}</p>
            )}
          </div>
          <NavBar
            step={step}
            onBack={goBack}
            onNext={handleSynthesize}
            nextDisabled={syncing || overLimit || !text.trim()}
            nextLabel={syncing ? "Synthesizing…" : "Synthesize"}
          />
        </Panel>

        <Panel title="Listen, then record yourself" subtitle="Play the target, shadow it, and hit Analyze.">
          <div className="w-full max-w-2xl space-y-4">
            {audioUrl && timing ? (
              <KaraokePlayer src={audioUrl} timing={timing} />
            ) : (
              <p className="text-sm text-slate-400">No audio yet — go back and synthesize.</p>
            )}
            {cacheKey && (
              <>
                <Recorder onSubmit={handleAnalyze} submitting={analyzing} />
                {analyzeError && (
                  <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-600">
                    {analyzeError}
                  </p>
                )}
              </>
            )}
          </div>
          <NavBar step={step} onBack={goBack} hideNext />
        </Panel>

        <Panel title="Pronunciation" subtitle="Per-word accuracy from Azure Speech (opt-in).">
          <div className="w-full max-w-3xl">
            {analysis ? (
              <PronunciationPanel analysis={analysis} />
            ) : (
              <p className="text-sm text-slate-400">No analysis yet.</p>
            )}
          </div>
          <NavBar step={step} onBack={goBack} onNext={goNext} nextLabel="Continue" />
        </Panel>

        <Panel title="Pace match">
          <div className="w-full max-w-3xl">
            {analysis ? (
              <FeedbackPanel analysis={analysis} />
            ) : (
              <p className="text-sm text-slate-400">No analysis yet.</p>
            )}
          </div>
          <NavBar step={step} onBack={goBack} onNext={restart} nextLabel="Start over" />
        </Panel>
      </div>
    </div>
  );
}

function Panel({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
}) {
  return (
    <section
      className="flex h-full shrink-0 flex-col items-center justify-center px-6 py-10"
      style={{ width: `${100 / TOTAL_STEPS}%` }}
    >
      <div className="flex flex-1 w-full flex-col items-center justify-center gap-8">
        <header className="w-full max-w-2xl text-center">
          <h1 className="text-3xl font-semibold tracking-tight">{title}</h1>
          {subtitle && <p className="mt-2 text-sm text-slate-500">{subtitle}</p>}
        </header>
        {children}
      </div>
    </section>
  );
}

function NavBar({
  step,
  onBack,
  onNext,
  nextDisabled,
  nextLabel = "Continue",
  hideNext,
}: {
  step: number;
  onBack: () => void;
  onNext?: () => void;
  nextDisabled?: boolean;
  nextLabel?: string;
  hideNext?: boolean;
}) {
  return (
    <div className="flex w-full max-w-lg items-center justify-between pt-4">
      <button
        type="button"
        onClick={onBack}
        disabled={step === 0}
        className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-30"
      >
        Back
      </button>
      <span className="text-xs text-slate-400">
        {step + 1} / {TOTAL_STEPS}
      </span>
      {hideNext || !onNext ? (
        <span className="w-[92px]" />
      ) : (
        <button
          type="button"
          onClick={onNext}
          disabled={nextDisabled}
          className="rounded-md bg-slate-800 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-40 transition-colors"
        >
          {nextLabel}
        </button>
      )}
    </div>
  );
}
