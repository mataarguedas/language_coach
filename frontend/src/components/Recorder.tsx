import { useRecorder } from "../lib/useRecorder";
import { MAX_RECORDING_MS } from "../lib/types";

interface Props {
  /** Called with the finalised recording once the user is happy with it. */
  onSubmit: (blob: Blob, mimeType: string | null) => void;
  /** True while the parent is awaiting the analyze API. Disables submit. */
  submitting?: boolean;
  disabled?: boolean;
}

function formatMs(ms: number): string {
  const s = Math.floor(ms / 1000);
  const tenths = Math.floor((ms % 1000) / 100);
  return `${s}.${tenths}s`;
}

/**
 * Language-blind recording UI: idle → recording → stopped → playback.
 * Enforces a hard clip length via useRecorder's auto-stop.
 */
export default function Recorder({ onSubmit, submitting, disabled }: Props) {
  const rec = useRecorder({ maxDurationMs: MAX_RECORDING_MS });
  const progressPct = Math.min(
    100,
    (rec.elapsedMs / MAX_RECORDING_MS) * 100,
  );

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-5 space-y-4">
      <div className="flex items-baseline justify-between">
        <p className="text-xs font-medium text-slate-500">Shadowing</p>
        <p className="text-xs text-slate-400">
          Max {Math.round(MAX_RECORDING_MS / 1000)}s
        </p>
      </div>

      {rec.state === "idle" && (
        <button
          type="button"
          onClick={rec.start}
          disabled={disabled}
          className="w-full rounded-md bg-red-600 py-2.5 text-sm font-medium text-white hover:bg-red-500 disabled:opacity-40 transition-colors"
        >
          ● Record
        </button>
      )}

      {rec.state === "requesting" && (
        <p className="text-sm text-slate-500">Waiting for microphone…</p>
      )}

      {rec.state === "recording" && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-2 text-sm font-medium text-red-600">
              <span className="inline-block h-2.5 w-2.5 animate-pulse rounded-full bg-red-600" />
              Recording {formatMs(rec.elapsedMs)}
            </span>
            <button
              type="button"
              onClick={rec.stop}
              className="rounded-md bg-slate-800 px-4 py-1.5 text-sm font-medium text-white hover:bg-slate-700"
            >
              Stop
            </button>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded bg-slate-100">
            <div
              className="h-full bg-red-500 transition-[width] duration-100"
              style={{ width: `${progressPct}%` }}
              aria-hidden
            />
          </div>
        </div>
      )}

      {rec.state === "stopped" && rec.blobUrl && (
        <div className="space-y-3">
          <p className="text-xs text-slate-500">
            Recorded {formatMs(rec.elapsedMs)}
            {rec.mimeType ? ` · ${rec.mimeType.split(";")[0]}` : ""}
          </p>
          {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
          <audio controls src={rec.blobUrl} className="w-full" />
          <div className="flex gap-2">
            <button
              type="button"
              onClick={rec.reset}
              disabled={submitting}
              className="flex-1 rounded-md border border-slate-300 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-40"
            >
              Retake
            </button>
            <button
              type="button"
              onClick={() => rec.blob && onSubmit(rec.blob, rec.mimeType)}
              disabled={submitting || !rec.blob}
              className="flex-1 rounded-md bg-slate-800 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-40"
            >
              {submitting ? "Analyzing…" : "Analyze"}
            </button>
          </div>
        </div>
      )}

      {rec.state === "error" && (
        <div className="space-y-2">
          <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-600">
            {rec.error ?? "Recording failed."}
          </p>
          <button
            type="button"
            onClick={rec.reset}
            className="w-full rounded-md border border-slate-300 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Try again
          </button>
        </div>
      )}
    </div>
  );
}
