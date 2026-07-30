import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Recorder state machine — language-agnostic.
 *
 *      ┌─────────┐   start()   ┌───────────┐  granted   ┌─────────────┐
 *      │  idle   │────────────▶│ requesting│───────────▶│  recording  │
 *      └─────────┘             └───────────┘            └─────────────┘
 *           ▲                        │ denied /                │ stop() /
 *           │                        │ error                   │ auto-stop
 *           │ reset()                ▼                         ▼
 *           │                    ┌───────┐                ┌──────────┐
 *           └────────────────────│ error │◀──────────────│ stopped   │
 *                                └───────┘   reset()      └──────────┘
 *
 * Auto-stop fires when elapsed ≥ ``maxDurationMs``.
 */
export type RecorderState =
  | "idle"
  | "requesting"
  | "recording"
  | "stopped"
  | "error";

export interface UseRecorderOptions {
  maxDurationMs?: number;
  mimeType?: string;
}

export interface UseRecorderResult {
  state: RecorderState;
  blob: Blob | null;
  blobUrl: string | null;
  mimeType: string | null;
  elapsedMs: number;
  error: string | null;
  start: () => Promise<void>;
  stop: () => void;
  reset: () => void;
}

const DEFAULT_MAX_MS = 30_000;
const PREFERRED_MIME = "audio/webm;codecs=opus";
const FALLBACK_MIMES = ["audio/webm", "audio/ogg;codecs=opus", "audio/ogg"];

function pickMimeType(preferred?: string): string | undefined {
  const isSupported = (t: string) =>
    typeof MediaRecorder !== "undefined" &&
    typeof MediaRecorder.isTypeSupported === "function" &&
    MediaRecorder.isTypeSupported(t);

  if (preferred && isSupported(preferred)) return preferred;
  if (isSupported(PREFERRED_MIME)) return PREFERRED_MIME;
  for (const t of FALLBACK_MIMES) {
    if (isSupported(t)) return t;
  }
  return undefined; // let the browser pick a default
}

export function useRecorder(
  options: UseRecorderOptions = {},
): UseRecorderResult {
  const maxDurationMs = options.maxDurationMs ?? DEFAULT_MAX_MS;

  const [state, setState] = useState<RecorderState>("idle");
  const [blob, setBlob] = useState<Blob | null>(null);
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [mimeType, setMimeType] = useState<string | null>(null);
  const [elapsedMs, setElapsedMs] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const startedAtRef = useRef<number>(0);
  const autoStopTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const tickTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const cleanupStream = useCallback(() => {
    if (streamRef.current) {
      for (const track of streamRef.current.getTracks()) track.stop();
      streamRef.current = null;
    }
    if (autoStopTimerRef.current) {
      clearTimeout(autoStopTimerRef.current);
      autoStopTimerRef.current = null;
    }
    if (tickTimerRef.current) {
      clearInterval(tickTimerRef.current);
      tickTimerRef.current = null;
    }
  }, []);

  const revokeBlobUrl = useCallback((url: string | null) => {
    if (url) URL.revokeObjectURL(url);
  }, []);

  const stop = useCallback(() => {
    const rec = recorderRef.current;
    if (rec && rec.state !== "inactive") {
      // onstop handler completes the transition to "stopped".
      rec.stop();
    }
  }, []);

  const start = useCallback(async () => {
    if (state === "recording" || state === "requesting") return;

    // Any previous blob URL is discarded when starting a fresh take.
    revokeBlobUrl(blobUrl);
    setBlob(null);
    setBlobUrl(null);
    setError(null);
    setElapsedMs(0);
    setState("requesting");

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : "Microphone access denied.";
      setError(msg);
      setState("error");
      return;
    }
    streamRef.current = stream;

    const chosenMime = pickMimeType(options.mimeType);
    let recorder: MediaRecorder;
    try {
      recorder = chosenMime
        ? new MediaRecorder(stream, { mimeType: chosenMime })
        : new MediaRecorder(stream);
    } catch (err) {
      cleanupStream();
      const msg =
        err instanceof Error
          ? err.message
          : "MediaRecorder is not supported in this browser.";
      setError(msg);
      setState("error");
      return;
    }
    recorderRef.current = recorder;
    setMimeType(recorder.mimeType || chosenMime || null);
    chunksRef.current = [];

    recorder.ondataavailable = (e: BlobEvent) => {
      if (e.data && e.data.size > 0) chunksRef.current.push(e.data);
    };

    recorder.onerror = () => {
      cleanupStream();
      setError("Recorder error.");
      setState("error");
    };

    recorder.onstop = () => {
      const type = recorder.mimeType || chosenMime || "audio/webm";
      const result = new Blob(chunksRef.current, { type });
      chunksRef.current = [];
      const url = URL.createObjectURL(result);
      cleanupStream();
      setBlob(result);
      setBlobUrl(url);
      setState("stopped");
    };

    startedAtRef.current = Date.now();
    setState("recording");
    recorder.start();

    autoStopTimerRef.current = setTimeout(() => {
      // Auto-stop when the max clip length is reached.
      const rec = recorderRef.current;
      if (rec && rec.state !== "inactive") rec.stop();
    }, maxDurationMs);

    tickTimerRef.current = setInterval(() => {
      setElapsedMs(Date.now() - startedAtRef.current);
    }, 100);
  }, [
    blobUrl,
    cleanupStream,
    maxDurationMs,
    options.mimeType,
    revokeBlobUrl,
    state,
  ]);

  const reset = useCallback(() => {
    if (recorderRef.current && recorderRef.current.state !== "inactive") {
      recorderRef.current.stop();
    }
    cleanupStream();
    revokeBlobUrl(blobUrl);
    setBlob(null);
    setBlobUrl(null);
    setError(null);
    setElapsedMs(0);
    setState("idle");
  }, [blobUrl, cleanupStream, revokeBlobUrl]);

  // Release the object URL when the hook unmounts.
  useEffect(() => {
    return () => {
      cleanupStream();
      revokeBlobUrl(blobUrl);
    };
    // Only on unmount — blobUrl captured in the closure at unmount time is fine.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return {
    state,
    blob,
    blobUrl,
    mimeType,
    elapsedMs,
    error,
    start,
    stop,
    reset,
  };
}
