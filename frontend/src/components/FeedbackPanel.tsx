import type { ProsodyFeatures, ShadowAnalysis } from "../lib/types";

interface Props {
  analysis: ShadowAnalysis;
}

function scoreColor(score: number): string {
  if (score >= 85) return "bg-emerald-500";
  if (score >= 65) return "bg-amber-500";
  return "bg-red-500";
}

function scoreLabel(score: number): string {
  if (score >= 85) return "Great pace";
  if (score >= 65) return "Close";
  return "Off pace";
}

function fmtDuration(s: number): string {
  return `${s.toFixed(2)}s`;
}

function ProsodyColumn({
  title,
  features,
}: {
  title: string;
  features: ProsodyFeatures;
}) {
  return (
    <div className="rounded-md border border-slate-200 bg-slate-50 p-3 space-y-1.5">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
        {title}
      </p>
      <div className="grid grid-cols-2 gap-x-2 gap-y-1 text-sm">
        <span className="text-slate-500">Duration</span>
        <span className="text-right font-medium text-slate-800">
          {fmtDuration(features.duration_s)}
        </span>
        <span className="text-slate-500">Speaking rate</span>
        <span className="text-right font-medium text-slate-800">
          {features.speaking_rate.toFixed(1)}
        </span>
        <span className="text-slate-500">Pauses</span>
        <span className="text-right font-medium text-slate-800">
          {features.pause_count}
        </span>
      </div>
    </div>
  );
}

export default function FeedbackPanel({ analysis }: Props) {
  const { prosody } = analysis;
  const score = Math.round(prosody.pace_match_score);

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-5 space-y-5">
      <div>
        <div className="flex items-baseline justify-between">
          <p className="text-xs font-medium text-slate-500">Pace match</p>
          <p className="text-sm font-medium text-slate-700">
            {scoreLabel(score)} · {score}/100
          </p>
        </div>
        <div
          className="mt-2 h-2 w-full overflow-hidden rounded bg-slate-100"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={score}
          aria-label="Pace match score"
        >
          <div
            className={`h-full ${scoreColor(score)} transition-[width] duration-500`}
            style={{ width: `${score}%` }}
          />
        </div>
      </div>

      <ul className="space-y-1.5">
        {prosody.tips.map((tip, i) => (
          <li
            key={i}
            className="rounded-md bg-slate-50 px-3 py-2 text-sm text-slate-700"
          >
            {tip}
          </li>
        ))}
      </ul>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <ProsodyColumn title="Target" features={prosody.target} />
        <ProsodyColumn title="You" features={prosody.learner} />
      </div>
    </div>
  );
}
