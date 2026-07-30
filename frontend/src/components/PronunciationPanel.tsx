import type { PronunciationWord, ShadowAnalysis } from "../lib/types";

interface Props {
  analysis: ShadowAnalysis;
}

// Same bands FeedbackPanel uses for pace-match — kept in sync deliberately
// so overall/pace numbers are visually comparable.
function overallColor(score: number): string {
  if (score >= 85) return "bg-emerald-500";
  if (score >= 65) return "bg-amber-500";
  return "bg-red-500";
}

function overallLabel(score: number): string {
  if (score >= 85) return "Great";
  if (score >= 65) return "Close";
  return "Needs work";
}

function chipClasses(word: PronunciationWord): string {
  const base =
    "inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-sm font-medium";

  // Status badges take precedence over score bands — an omitted word has no
  // meaningful accuracy score, and an inserted word wasn't in the target.
  if (word.status === "omitted") {
    return `${base} border-dashed border-slate-400 bg-slate-50 text-slate-500`;
  }
  if (word.status === "inserted") {
    return `${base} border-dotted border-sky-400 bg-sky-50 text-sky-700`;
  }

  const s = word.accuracy_score;
  if (s >= 85) return `${base} border-emerald-200 bg-emerald-100 text-emerald-800`;
  if (s >= 65) return `${base} border-amber-200 bg-amber-100 text-amber-800`;
  return `${base} border-red-200 bg-red-100 text-red-800`;
}

export default function PronunciationPanel({ analysis }: Props) {
  const { pronunciation, pronunciation_error } = analysis;

  // Error takes precedence over the empty state: an actual attempt happened
  // but Azure failed — tell the user *why*, without dropping their prosody
  // feedback on the next panel.
  if (pronunciation === null && pronunciation_error) {
    return (
      <div
        className="rounded-lg border border-amber-200 bg-amber-50 p-5 space-y-2"
        data-testid="pronunciation-error"
        role="alert"
      >
        <p className="text-xs font-semibold uppercase tracking-wide text-amber-700">
          Pronunciation unavailable
        </p>
        <p className="text-sm text-amber-800">{pronunciation_error}</p>
        <p className="text-xs text-amber-700">
          Your pace-match feedback is still available on the next step.
        </p>
      </div>
    );
  }

  if (pronunciation === null) {
    return (
      <div
        className="rounded-lg border border-slate-200 bg-white p-5 space-y-2"
        data-testid="pronunciation-empty"
      >
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          Pronunciation
        </p>
        <p className="text-sm text-slate-600">
          Add your Azure Speech key and region on the first step to enable
          pronunciation scoring.
        </p>
      </div>
    );
  }

  const score = Math.round(pronunciation.overall_score);
  const bar = overallColor(score);
  const label = overallLabel(score);

  return (
    <div
      className="rounded-lg border border-slate-200 bg-white p-5 space-y-5"
      data-testid="pronunciation-populated"
    >
      <div>
        <div className="flex items-baseline justify-between">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Pronunciation
          </p>
          <p className="text-sm font-medium text-slate-700">
            {label} · {score}/100
          </p>
        </div>
        <div className="mt-3 flex items-baseline gap-3">
          <span
            className={`inline-flex items-baseline rounded-md px-3 py-1 text-4xl font-semibold text-white ${bar}`}
            aria-label={`Overall pronunciation score ${score} percent`}
          >
            {score}%
          </span>
        </div>
      </div>

      <div>
        <p className="text-xs font-medium text-slate-500 mb-2">
          Per-word accuracy
        </p>
        <div className="flex flex-wrap gap-2" role="list">
          {pronunciation.words.map((word, i) => (
            <span
              key={i}
              role="listitem"
              data-status={word.status}
              className={chipClasses(word)}
              aria-label={`${word.text}, ${word.status}, ${Math.round(
                word.accuracy_score,
              )} percent`}
            >
              <span>{word.text}</span>
              {word.status === "omitted" && (
                <span className="text-[10px] uppercase tracking-wide text-slate-500">
                  omitted
                </span>
              )}
              {word.status === "inserted" && (
                <span className="text-[10px] uppercase tracking-wide text-sky-600">
                  inserted
                </span>
              )}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
