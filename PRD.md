# PRD — Pronunciation Coach (Mandarin · Spanish · English)

## 1. Overview

A voice-driven web app for language learners. Users type or paste text in **Mandarin, Spanish, or English** and hear it spoken in natural, native-sounding audio at adjustable speeds, with word-level karaoke highlighting synced to playback. A **shadowing mode** plays a target phrase, records the learner repeating it via the browser, and returns two kinds of feedback: **prosodic** (pace, duration, pause placement) and **per-word pronunciation scoring** from a hosted assessment provider.

This is a **portfolio/learning project**: optimize for a clean, buildable, single-machine-friendly architecture over enterprise robustness. Stateless, single-session, no accounts.

## 2. Goals & Non-Goals

### Goals
- High-quality TTS in **three languages** (Mandarin, Spanish, English) via **Fish Audio hosted API**, with a fixed set of curated native voices **per language**.
- Native prosody/speed control (Fish-side), not client-side pitch-distorting playback rate.
- Word-boundary timestamps driving **karaoke-style highlighting** during playback, using **language-aware segmentation**.
- **Shadowing mode**: play → record (MediaRecorder) → upload → prosodic comparison **+ per-word pronunciation scoring** → visual feedback. Prosody is language-agnostic; pronunciation scoring uses one hosted provider that natively supports all three languages (locale param, not per-language code paths).
- **Per-word pronunciation scoring** in all three languages via **Azure Speech Pronunciation Assessment** (BYOK). Mandarin includes tone accuracy where the provider supplies it. Word-level scoring only in the MVP; per-phoneme drill-down is optional/future.
- **Local audio caching** so identical (text + language + voice + speed) requests never re-bill Fish. Pronunciation results are cached per (target + learner audio hash) so re-analyzing the same recording never re-bills Azure.
- **BYOK**: users supply their own OpenAI, Fish Audio, and Azure Speech API keys. The Azure key is only required when running the pronunciation step.

### Non-Goals
- No open-ended STT — pronunciation is always scored against a known target string (the text the user synthesized), never free transcription of learner audio.
- No per-phoneme pronunciation UI in the MVP (word-level scores only; phoneme-level drill-down is a future add).
- No voice cloning (fixed voices only).
- No automatic language detection in the MVP — the user selects the language explicitly (see Risks for the rationale and a possible later add).
- No translation between languages (this is a pronunciation tool, not a translator).
- No user accounts, saved history, or cross-session progress.
- No realtime streaming TTS (request → full clip → play).
- No mobile-native app (responsive web only).

## 3. Users & Core Flows

**Primary user:** a self-directed language learner (Mandarin, Spanish, or English) practicing listening and speaking.

### Flow A — Listen & Read
1. User selects a **language**, types/pastes text, and picks a voice and speed. Only voices for the selected language are shown.
2. App requests word boundaries (language-aware segmentation) + audio (Fish TTS).
3. Audio plays; each word highlights in sync via the computed timing schedule.

### Flow B — Shadowing
1. User selects a phrase (from their input) as the target.
2. App plays the native audio.
3. User records themselves repeating it (MediaRecorder).
4. Recording uploads to FastAPI in a single request; backend extracts prosodic features **and** calls the pronunciation provider with the target text + learner audio + language locale.
5. App shows two panels of feedback:
   - **Pace match** — total duration, speech rate, pause count/placement, plus a simple pace-match score and guidance ("you were 30% faster; try slowing the second half"). Language-agnostic.
   - **Pronunciation** — per-word accuracy scores with color coding (green/amber/red) and an overall pronunciation percentage. Same visual across all three languages; Mandarin word scores reflect tone accuracy where Azure supplies it.
   If the user has not supplied an Azure key, the pace-match panel still renders; the pronunciation panel shows a "provide Azure key to enable" state.

## 4. Functional Requirements

### 4.1 Language Selection & Text Input
- User explicitly selects one of: **Mandarin (`zh`)**, **Spanish (`es`)**, **English (`en`)**. Language is a required parameter on every synthesis/segmentation request.
- Accept typed or pasted text. For Mandarin, accept Simplified/Traditional. For Spanish/English, accept standard input including accented characters (á, é, í, ñ, ü, etc.).
- Character-count guard (e.g. max ~500 chars per synthesis) to bound cost/latency, applied per language.

### 4.2 Voice & Speed
- Fixed catalog of native voices (curated Fish `reference_id`s), **grouped by language**. Each voice has a display label, its language code, and a short sample.
- The frontend only offers voices matching the selected language; the backend validates that the requested voice belongs to the requested language and rejects mismatches with a 4xx.
- Speed control mapped to Fish's native prosody parameters (discrete presets, e.g. 0.7× / 0.85× / 1.0× / 1.15×), each producing a distinct cached clip. Presets are shared across languages.

### 4.3 TTS + Caching
- Cache key = hash(text + **language** + voice_id + speed_preset).
- Cache hit → serve local file, zero API cost.
- Cache miss → call Fish, persist audio (e.g. MP3) + metadata locally, then serve.
- Cache is content-addressable on disk; no DB required (JSON sidecar or SQLite index optional).

### 4.4 Word Boundaries / Karaoke (language-aware)
- Segmentation strategy depends on language:
  - **Mandarin (`zh`):** no whitespace word boundaries → use the **OpenAI LLM** to segment the text into ordered words/tokens.
  - **Spanish (`es`) / English (`en`):** whitespace- and punctuation-delimited → segment **locally** (deterministic tokenizer, no LLM call, no API cost). Handle contractions/clitics and punctuation reasonably.
- A single `segment(text, language)` service abstracts this: it dispatches to the LLM segmenter for `zh` and the local tokenizer for `es`/`en`, returning the same token-list shape either way.
- Timing model (all languages): since hosted Fish returns audio (not per-word timestamps), derive per-word timing by **proportional allocation** across the clip duration weighted by token length, refined by punctuation-based pause insertion. (Documented as an approximation; good enough for highlighting UX.)
- Frontend highlights the active word using the audio element's `currentTime` against the computed schedule. UI is identical across languages.

### 4.5 Shadowing / Feedback
Record via `MediaRecorder` (WebM/Opus), upload as multipart to FastAPI in a **single** request. The backend runs prosody and pronunciation independently and returns both in one response so the frontend makes one round-trip.

#### 4.5a Prosody (language-agnostic)
- Backend uses `librosa`/`parselmouth` to extract from **both** target and learner audio:
  - total duration
  - speaking rate (voiced-frames / time)
  - pause segments (silence detection) — count and rough placement
  - overall energy envelope for a lightweight pace-alignment score
- Returns a `prosody` block: features for target + learner, a normalized 0–100 "pace match" score, and human-readable tips.
- Acoustic and **language-independent** — same code path serves all three languages. No transcription, no word accuracy here.
- Prosody runs regardless of whether the Azure key is present.

#### 4.5b Pronunciation (single provider, language-parameterized)
- Provider: **Azure Speech Pronunciation Assessment** (REST). One integration serves all three languages; per-language behavior is a locale string (`zh-CN`, `es-ES`, `en-US`) on the request, not a code branch.
- Inputs: learner audio, the target text the user synthesized, language locale.
- Outputs (MVP): overall accuracy score (0–100), per-word accuracy score, per-word status (correct / mispronounced / omitted / inserted). Per-phoneme scores are returned by the provider but not surfaced in the UI in the MVP.
- Returned as a `pronunciation` block in the same response as prosody.
- If the Azure key is missing, the backend omits the `pronunciation` block (or returns `pronunciation: null`) and the prosody block is still populated — pronunciation is a strict opt-in, not a hard dependency.
- No open-ended STT: the target text is always known (it's what the user just synthesized), so Azure runs in reference-scored mode.

### 4.6 BYOK & Keys
- User enters OpenAI, Fish, and Azure Speech keys in the UI (session-only, kept in memory / sessionStorage, never persisted server-side beyond the request).
- Keys sent per-request to FastAPI, which forwards them to providers; backend never logs keys.
- Optionality:
  - **Fish key** — always required (all TTS).
  - **OpenAI key** — required only for Mandarin (segmentation). Spanish/English work without it.
  - **Azure Speech key** — required only for the pronunciation step. Prosody-only shadowing works without it. The UI should make this clear.

## 5. Architecture

```
React (Vercel)  ──HTTP──►  FastAPI (Railway, Docker)  ──►  Fish Audio API (TTS, all langs)
   │  MediaRecorder                    │                ├►  OpenAI API (zh segmentation only)
   │  <audio> + karaoke UI             │                └►  Azure Speech Pronunciation Assessment
   │  language + voice pickers         ├──►  Local tokenizer (es/en segmentation, no API)
   └───────────────────────────────────┴──►  Local audio cache (disk + optional SQLite)
                                                 + pronunciation result cache
```

- **Frontend (React/Vite, Vercel):** language picker, input, voice/speed pickers (filtered by language), audio player with karaoke, recorder, feedback view. Talks to backend via REST.
- **Backend (FastAPI, Docker on Railway):** endpoints for synthesis, segmentation, shadowing analysis; owns caching, language-aware segmentation dispatch, and provider calls.
- **Cache:** persisted on Railway volume. Stateless request/response otherwise.

### Key Endpoints
| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/segment` | language-aware word segmentation → token list (LLM for `zh`, local for `es`/`en`) |
| `POST` | `/api/synthesize` | text+language+voice+speed → cached/generated audio (+ timing schedule) |
| `GET`  | `/api/voices` | fixed voice catalog; supports `?language=` filter |
| `GET`  | `/api/languages` | supported languages metadata (code, label) |
| `POST` | `/api/shadow/analyze` | multipart learner audio + target cache key → single response with `prosody` and (if Azure key present) `pronunciation` blocks |
| `GET`  | `/api/health` | health check |

## 6. Tech Stack

- **Frontend:** React + Vite, TypeScript, Tailwind. Web Audio / `<audio>` for playback, `MediaRecorder` for capture.
- **Backend:** FastAPI (Python 3.11+), `uvicorn`, `httpx` (async provider calls), `librosa` + `praat-parselmouth` + `numpy` for prosody, `pydantic` models.
- **TTS:** Fish Audio hosted API (multilingual voices).
- **LLM:** OpenAI (Mandarin segmentation only).
- **Segmentation (es/en):** local deterministic tokenizer (no external dependency required; a lightweight rule-based splitter is sufficient).
- **Pronunciation scoring:** Azure Speech Pronunciation Assessment via REST (`httpx`). One provider covers all three languages; the SDK is not required — REST + audio upload keeps the server dependencies light.
- **Infra:** Vercel (frontend), Railway + Docker (backend), Railway volume for cache.

## 7. Milestones

1. **M1 — TTS core (multilingual):** language + voice catalog (all three languages), `/synthesize`, disk cache keyed by language, basic player. (No karaoke yet.)
2. **M2 — Karaoke (language-aware):** `/segment` with LLM-for-`zh` / local-for-`es`/`en` dispatch, timing schedule, synced highlighting.
3. **M3 — Shadowing (prosody):** recorder, `/shadow/analyze` returning a `prosody` block, pace-match feedback UI (works across all languages).
4. **M4 — BYOK + polish:** key entry UX (OpenAI optional unless Mandarin, Azure optional unless pronunciation is used), error states, deploy to Vercel/Railway, Docker hardening.
5. **M5 — Pronunciation scoring:** Azure integration in `services/pronunciation.py`, extend `/shadow/analyze` response with a `pronunciation` block, new full-page slider panel between "playback + record" and "pace match" showing per-word scores and an overall pronunciation percentage. Cache pronunciation results by (target cache key + learner audio hash).

## 8. Risks & Mitigations

- **Word-timing accuracy:** hosted Fish lacks per-word timestamps → proportional-allocation approximation; acceptable for a learning tool, documented as such. Applies equally to all languages.
- **Language/voice mismatch:** user could request an `es` voice with `zh` text → backend validates voice belongs to selected language and rejects mismatches clearly.
- **No auto language detection:** requiring explicit selection avoids misdetection bugs and keeps segmentation deterministic. Auto-detection could be added later (LLM or a small local classifier) without changing the storage/cache model.
- **Prosody comparison is fuzzy:** keep scoring transparent and advisory ("guidance," not "grade"); avoid over-claiming precision. Language-independent by design.
- **BYOK key handling:** never persist/log keys; document the trust model plainly in the UI. Clarify OpenAI key is only needed for Mandarin karaoke.
- **Cost surprises:** caching + char limits + discrete speed presets bound Fish spend; local segmentation for `es`/`en` avoids unnecessary LLM calls. Pronunciation results are cached per (target cache key + learner audio hash) so retries on the same recording never re-bill Azure; the existing recording-duration cap doubles as the Azure cost cap.
- **CORS / upload size:** configure FastAPI CORS for the Vercel origin; cap upload duration.
- **Pronunciation quality is provider-dependent:** Mandarin tone scoring specifically depends on Azure's model. Document this in the UI ("guidance, not a grade") and keep score display fuzzy enough (color bands, not decimals) to avoid over-claiming precision.
- **Learner audio handling:** learner audio is hashed in memory to build the pronunciation cache key, then discarded. It is **never** written to disk. Only the resulting JSON scores are cached.

## 9. Success Criteria

- All three languages synthesize correctly with their own curated voices.
- Identical synthesis requests hit cache with zero repeat billing (cache correctly discriminates by language).
- Karaoke highlight tracks audio within a tolerance that "feels" synced in every language; `es`/`en` segmentation costs zero API calls.
- Shadowing returns actionable pace feedback within a couple seconds of upload, regardless of language.
- Pronunciation scoring returns per-word results within a couple seconds of upload, in all three languages; re-analyzing the same (target, learner audio) pair hits cache with zero repeat Azure billing.
- With no Azure key present, the shadowing flow still succeeds and returns prosody-only feedback (pronunciation is a strict opt-in).
- Full stack deploys cleanly to Vercel + Railway with BYOK (Fish + optional OpenAI + optional Azure).
