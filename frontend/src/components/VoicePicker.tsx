import type { Voice } from "../lib/types";

interface Props {
  voices: Voice[];
  value: string;
  onChange: (voiceId: string) => void;
  loading: boolean;
}

export default function VoicePicker({ voices, value, onChange, loading }: Props) {
  return (
    <div className="space-y-1">
      <label className="block text-xs font-medium text-slate-600">Voice</label>
      {loading ? (
        <p className="text-sm text-slate-400">Loading voices…</p>
      ) : voices.length === 0 ? (
        <p className="text-sm text-slate-400">No voices available.</p>
      ) : (
        <select
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 focus:border-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-500"
        >
          {voices.map((v) => (
            <option key={v.reference_id} value={v.reference_id}>
              {v.label}
            </option>
          ))}
        </select>
      )}
    </div>
  );
}
