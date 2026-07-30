# CLAUDE.md — Pronunciation Coach (Mandarin · Spanish · English)

Engineering guidance for AI-assisted work on this repo. Read before generating or editing code.

## What this project is

Voice-driven pronunciation practice app supporting **three languages: Mandarin (`zh`), Spanish (`es`), and English (`en`)**. Users select a language, paste text → hear native-quality TTS at adjustable speeds with word-level karaoke highlighting. A shadowing mode plays a phrase, records the learner, and returns two things: **prosodic** feedback (pace/timing, language-agnostic) and **per-word pronunciation scores** from a single hosted provider (Azure Speech Pronunciation Assessment).

Portfolio/learning project. Favor clear, minimal, buildable code over enterprise machinery.

## Locked decisions (do not re-litigate)

- **Languages:** exactly three — `zh`, `es`, `en`. Language is an explicit, required parameter on synthesis/segmentation requests. **No auto-detection** in MVP; the user picks the language.
- **TTS:** Fish Audio **hosted API** only. No self-hosting, no voice cloning. Fixed catalog of native voices **grouped by language**.
- **Speed:** Fish **native prosody/speed** parameters, mapped to discrete presets shared across languages. Never client-side `playbackRate` for the "adjustable speed" feature (it distorts pitch).
- **Segmentation (LLM usage):** language-dependent.
  - `zh` → **OpenAI LLM** segments (no whitespace boundaries).
  - `es` / `en` → **local deterministic tokenizer**, no LLM, no API cost.
  - Both return the same token-list shape behind one `segment(text, language)` service.
- **Shadowing:** two independent outputs from a single upload/round-trip.
  - **Prosody** — duration, speaking rate, pauses. Acoustic and **language-agnostic**: one code path for all three languages. No STT.
  - **Pronunciation** — per-word accuracy scores from **Azure Speech Pronunciation Assessment**. One provider for all three languages; per-language behavior is a `locale` parameter (`zh-CN` / `es-ES` / `en-US`), **not** a dispatch. The target text is always the string the user just synthesized — Azure is called in reference-scored mode, never for open-ended transcription.
  - **Independence:** prosody must run even when the Azure key is missing. Pronunciation is a strict opt-in — if the key is absent, return `pronunciation: null` (or omit the block) alongside the populated `prosody` block. Never fail the whole request because pronunciation is unavailable.
  - **Scope:** word-level scores only in MVP. Azure returns per-phoneme data; ignore it in the response mapping until a phoneme drill-down is scoped.
  - No translation. No tone/word accuracy beyond what Azure supplies.
- **Recording:** browser `MediaRecorder` → single multipart upload to FastAPI (one request returns both prosody and pronunciation).
- **State:** stateless, single-session. No accounts, no DB of user data, no cross-session history.
- **Caching:**
  - Generated audio cached **locally on disk**; identical (text + **language** + voice + speed) never re-bills Fish.
  - Pronunciation results cached **locally on disk** keyed by `sha256(target_cache_key + learner_audio_hash)`; identical re-analysis never re-bills Azure. Learner audio itself is **never** written to disk — hash in memory, then discard.
- **Keys:** **BYOK** — user supplies Fish, OpenAI, and Azure Speech keys, sent per-request, never persisted or logged server-side.
  - **Fish** — always required.
  - **OpenAI** — only required for Mandarin segmentation.
  - **Azure Speech** — only required for the pronunciation step.
- **Deploy:** React on **Vercel**, FastAPI on **Railway** via **Docker**, cache on a Railway volume.

If a change seems to violate one of these, stop and flag it rather than silently redesigning.

## Repo layout

```
/frontend        React + Vite + TS + Tailwind
  /src
    /components   LanguagePicker, VoicePicker, SpeedControl, KaraokePlayer, Recorder,
                  FeedbackPanel, PronunciationPanel, KeyEntry
    /lib          api client, timing scheduler, audio utils
/backend         FastAPI
  /app
    main.py       app + CORS + router include
    /routers      segment.py, synthesize.py, voices.py, languages.py, shadow.py, health.py
    /services     fish.py, segmenter.py, cache.py, prosody.py, pronunciation.py, timing.py
      segmenter.py       dispatch: zh -> openai_seg, es/en -> local_tokenizer
      pronunciation.py   Azure Speech client (single provider, locale-parameterized)
    /models       pydantic schemas (Language enum + PronunciationResult live here)
    voices.py     fixed voice catalog (reference_ids + labels + language)
  Dockerfile
  requirements.txt
/PRD.md
/CLAUDE.md
```

## Language model (the core cross-cutting concept)

- Define a `Language` enum (`zh`, `es`, `en`) in one place; every synthesis/segment request carries it.
- `services/segmenter.py` is the single dispatch point:
  - `zh` → `openai_seg.segment(text, key)` (LLM)
  - `es` / `en` → `local_tokenizer.segment(text, language)` (rule-based, deterministic, no network)
  - Both return `list[Token]` with identical shape so downstream timing/karaoke code is language-blind.
- The voice catalog is keyed by language. Backend **must validate** that a requested `voice_id` belongs to the requested `language`; reject mismatch with a clear 4xx.
- Cache key **must include language**: `sha256(text + language + voice_id + speed_preset)`. A key that omits language is a bug (would collide across languages sharing a voice or identical strings).
- **Pronunciation is language-parameterized, not language-dispatched.** Do **not** mirror the segmenter pattern for pronunciation — there is one `services/pronunciation.py` calling one provider. Language enters as a locale string on the request payload (`zh-CN` / `es-ES` / `en-US`). Anyone reaching for a per-language branch here should stop and question it.

## Conventions

### Backend
- Python 3.11+, FastAPI, async endpoints. Use `httpx.AsyncClient` for all provider calls.
- All request/response bodies are pydantic models — no bare dicts across boundaries. Language is a typed enum, not a free string.
- Provider keys arrive per-request (headers `X-OpenAI-Key`, `X-Fish-Key`, `X-Azure-Speech-Key` + `X-Azure-Speech-Region`). **Never** log them, never write to disk, never put in cache keys.
- Key optionality is enforced per-endpoint:
  - OpenAI key only consumed on the `zh` segmentation path; `es`/`en` requests must succeed without it.
  - Azure key only consumed on the pronunciation path inside `/shadow/analyze`; prosody must still return when it's absent (return `pronunciation: null`, not a 4xx).
  - Missing a **required** key (Fish for synthesis, OpenAI for zh segmentation, Azure when pronunciation is actually invoked as a required step) → 4xx with a clear explanation. Never 500.
- Cache: content-addressable.
  - Audio cache key includes language (above). Store `<hash>.mp3` + `<hash>.json` (timing schedule + metadata). Check disk before any Fish call.
  - Pronunciation cache key: `sha256(target_cache_key + learner_audio_hash)`. Store `<hash>.json` only. Check disk before any Azure call. Never write learner audio to disk — hash the in-memory bytes, discard.
- Prosody in `services/prosody.py` using `librosa`/`parselmouth`. Keep feature extraction pure and unit-testable (take a file path / ndarray, return a dataclass). It is **language-independent** — never branch on language here.
- Pronunciation in `services/pronunciation.py`. Pure I/O layer around Azure REST. Returns a typed `PronunciationResult` dataclass/pydantic model with overall score + per-word scores + status. No language branching beyond building the locale string. Word-level fields only in the MVP; do not surface phoneme detail in the response schema yet (keep it out to prevent frontend from depending on it prematurely).
- `/shadow/analyze` orchestrates: run prosody unconditionally, run pronunciation only if the Azure key is present, return one response `{prosody, pronunciation}`. Do not fan out into two endpoints — keep the frontend to one round-trip.

### Frontend
- React function components + hooks, TypeScript strict.
- Language picker drives everything: selecting a language filters the voice list (only that language's voices) and tags outgoing requests. Changing language re-fetches/filters voices.
- Karaoke: a scheduler in `/lib` converts the backend timing schedule into active-word state driven by the `<audio>` element's `timeupdate` / `currentTime`. Don't recompute timing on the client — consume the backend schedule. Scheduler is language-blind.
- Recorder: `MediaRecorder` with Opus/WebM; enforce a max clip length; show record/stop/playback states. Identical across languages.
- Full-page slider flow — `PronunciationPanel` is a **new full-viewport panel inserted between "playback + record" and "pace match"**. It renders per-word chips colored by score plus an overall pronunciation percentage. If the response has `pronunciation: null` (no Azure key), the panel renders an "add your Azure key to enable pronunciation scoring" state and the flow still advances to the pace-match panel.
- One analyze round-trip: after the user hits Analyze in the Recorder, expect a single response with both `prosody` and (optionally) `pronunciation`. Store both, then slide through both panels. Do not issue two separate requests.
- Keys live in memory / `sessionStorage` only; clear on tab close. Surface that the OpenAI key is optional unless using Mandarin karaoke, and that the Azure key is optional unless the user wants pronunciation scoring.
- Tailwind for styling; keep components small and presentational where possible.

## Word timing (important nuance)

Hosted Fish does **not** return per-word timestamps. The karaoke schedule is an **approximation** for all languages:
1. `segment(text, language)` produces ordered tokens (LLM for `zh`, local tokenizer for `es`/`en`).
2. Backend allocates the clip duration across tokens proportionally to token length, inserting extra dwell at punctuation.
3. Frontend highlights against `currentTime`.

This is intentional and documented. Do **not** introduce STT/forced-alignment to "fix" it — out of scope. Small refinements to the allocation heuristic are fine and should stay language-agnostic.

## Testing

- Backend: pytest. Unit-test:
  - cache key stability **and language discrimination** (same text+voice+speed but different language → different keys).
  - segmenter dispatch: `zh` calls the (mocked) LLM; `es`/`en` never touch the network.
  - local tokenizer on Spanish/English fixtures (accents, punctuation, contractions).
  - prosody feature extraction on fixture WAVs (language-independent).
  - timing allocation.
  - pronunciation service: Azure is called with the right locale per language; missing Azure key → `pronunciation: null` and prosody still returns; pronunciation cache de-dupes repeated analyses of the same (target, learner) pair; malformed Azure response fails cleanly with a 4xx/5xx as appropriate (never a raw traceback to the client); learner audio is not persisted to disk.
  - `/shadow/analyze` orchestration: prosody-only response when Azure key is absent; both blocks when present; response schema shape stable in both cases.
  - Mock all provider HTTP calls — never hit Fish/OpenAI/Azure in tests.
- Frontend: component tests for the timing scheduler, the language→voice filtering, the recorder state machine, and the pronunciation panel (renders per-word chips + overall score; renders the "add Azure key" state when `pronunciation` is null).

## Security / cost guardrails

- Enforce char limit on synthesis input and duration cap on uploads (per request, all languages). The upload duration cap doubles as the Azure pronunciation cost cap.
- Always check cache before Fish. A cache miss that should've hit is a bug. Verify the cache key includes language.
- Always check the pronunciation cache before Azure. A cache miss for the same (target cache key + learner audio hash) that should've hit is a bug.
- Never call OpenAI for `es`/`en` — that's wasted spend; segmentation there is local.
- Never call Azure when the client didn't supply the Azure key — pronunciation is opt-in, not silently enabled.
- Never persist learner audio to disk. Hash the in-memory bytes to build the cache key, then discard. Only pronunciation result JSON gets cached.
- Never persist BYOK keys. Never include keys in cache keys, logs, or error messages.
- Configure CORS to the known Vercel origin(s) only.

## When unsure

Ask before: adding a database, adding auth, adding open-ended STT (reference-scored pronunciation via Azure is in scope; free transcription is not), adding language auto-detection, adding a fourth language, adding translation, switching TTS speed to client-side, surfacing per-phoneme scores in the UI, swapping the pronunciation provider, persisting learner audio to disk, or persisting anything user-specific. All of these contradict locked decisions.
