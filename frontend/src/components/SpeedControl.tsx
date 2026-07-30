import { SPEED_PRESETS } from "../lib/types";

interface Props {
  value: number;
  onChange: (speed: number) => void;
}

export default function SpeedControl({ value, onChange }: Props) {
  return (
    <div className="space-y-1">
      <label className="block text-center text-xs font-medium text-slate-600">Speed</label>
      <div className="flex justify-center gap-2">
        {SPEED_PRESETS.map((preset) => (
          <button
            key={preset.value}
            onClick={() => onChange(preset.value)}
            className={[
              "rounded-md border px-3 py-1.5 text-sm transition-colors",
              value === preset.value
                ? "border-slate-800 bg-slate-800 text-white"
                : "border-slate-300 bg-white text-slate-700 hover:border-slate-400 hover:bg-slate-50",
            ].join(" ")}
          >
            {preset.label}
          </button>
        ))}
      </div>
    </div>
  );
}
