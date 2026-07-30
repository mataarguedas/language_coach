import type { Language, LanguageMeta } from "../lib/types";

interface Props {
  languages: LanguageMeta[];
  value: Language;
  onChange: (lang: Language) => void;
}

export default function LanguagePicker({ languages, value, onChange }: Props) {
  return (
    <div className="space-y-1">
      <label className="block text-center text-xs font-medium text-slate-600">Language</label>
      <div className="flex justify-center gap-2">
        {languages.map((lang) => (
          <button
            key={lang.code}
            onClick={() => onChange(lang.code)}
            className={[
              "rounded-md border px-4 py-2 text-sm font-medium transition-colors",
              value === lang.code
                ? "border-slate-800 bg-slate-800 text-white"
                : "border-slate-300 bg-white text-slate-700 hover:border-slate-400 hover:bg-slate-50",
            ].join(" ")}
          >
            {lang.label}
          </button>
        ))}
      </div>
    </div>
  );
}
