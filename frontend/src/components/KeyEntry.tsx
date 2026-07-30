import { useEffect, useState } from "react";
import {
  clearKeys,
  getAzureKey,
  getAzureRegion,
  getFishKey,
  getOpenAiKey,
  setAzureKey,
  setAzureRegion,
  setFishKey,
  setOpenAiKey,
} from "../lib/keys";

interface Props {
  language: string;
  onChange: () => void;
}

export default function KeyEntry({ language, onChange }: Props) {
  const [fish, setFish] = useState(getFishKey);
  const [openai, setOpenai] = useState(getOpenAiKey);
  const [azure, setAzure] = useState(getAzureKey);
  const [azureRegion, setAzureRegionState] = useState(getAzureRegion);

  const hasFish = !!getFishKey();
  const hasOpenAi = !!getOpenAiKey();
  const hasAzure = !!getAzureKey() && !!getAzureRegion();
  const missingRequired = !hasFish || (language === "zh" && !hasOpenAi);

  const [open, setOpen] = useState(missingRequired);

  useEffect(() => {
    if (language === "zh" && !hasOpenAi) setOpen(true);
  }, [language, hasOpenAi]);

  function save() {
    setFishKey(fish.trim());
    setOpenAiKey(openai.trim());
    setAzureKey(azure.trim());
    setAzureRegion(azureRegion.trim());
    onChange();
    const stillMissing =
      !fish.trim() || (language === "zh" && !openai.trim());
    if (!stillMissing) setOpen(false);
  }

  function handleClear() {
    clearKeys();
    setFish("");
    setOpenai("");
    setAzure("");
    setAzureRegionState("");
    onChange();
    setOpen(true);
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-white">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between px-4 py-3 text-sm font-medium text-slate-700 hover:bg-slate-50"
      >
        <span className="flex items-center gap-2">
          <span>API Keys</span>
          {missingRequired ? (
            <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs text-amber-700">
              {!hasFish ? "Fish key required" : "OpenAI key needed for Mandarin"}
            </span>
          ) : (
            <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs text-emerald-700">
              configured
            </span>
          )}
          {hasAzure && (
            <span className="rounded-full bg-sky-100 px-2 py-0.5 text-xs text-sky-700">
              pronunciation enabled
            </span>
          )}
        </span>
        <span className="text-slate-400">{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="border-t border-slate-200 px-4 pb-4 pt-3 space-y-3">
          <Field
            label="Fish Audio key"
            value={fish}
            onChange={setFish}
            required
          />
          <Field
            label={
              language === "zh"
                ? "OpenAI key (required for Mandarin karaoke)"
                : "OpenAI key (only needed for Mandarin karaoke)"
            }
            value={openai}
            onChange={setOpenai}
            required={language === "zh"}
          />

          <div className="pt-2 border-t border-slate-100">
            <p className="text-xs text-slate-500 mb-2">
              Optional — only needed if you want per-word pronunciation scoring.
              Both fields are required together; leave blank to skip pronunciation
              and get pace-match feedback only.
            </p>
            <div className="space-y-3">
              <Field
                label="Azure Speech key (optional)"
                value={azure}
                onChange={setAzure}
                required={false}
              />
              <Field
                label="Azure Speech region (optional, e.g. westus, eastus)"
                value={azureRegion}
                onChange={setAzureRegionState}
                required={false}
                type="text"
              />
            </div>
          </div>

          <div className="flex gap-2 pt-1">
            <button
              onClick={save}
              disabled={!fish.trim()}
              className="rounded-md bg-slate-800 px-3 py-1.5 text-sm text-white hover:bg-slate-700 disabled:opacity-40"
            >
              Save
            </button>
            {(hasFish || hasOpenAi || hasAzure) && (
              <button
                onClick={handleClear}
                className="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50"
              >
                Clear
              </button>
            )}
          </div>
          <p className="text-xs text-slate-400">
            Keys are stored in sessionStorage and cleared when the tab closes.
            They are never sent to our servers except as request headers to
            Fish&nbsp;Audio, OpenAI, and Azure&nbsp;Speech.
          </p>
        </div>
      )}
    </div>
  );
}

interface FieldProps {
  label: string;
  value: string;
  onChange: (v: string) => void;
  required: boolean;
  type?: "password" | "text";
}

function Field({ label, value, onChange, required, type = "password" }: FieldProps) {
  return (
    <label className="block space-y-1">
      <span className="text-xs font-medium text-slate-600">
        {label}
        {required && <span className="ml-1 text-red-500">*</span>}
      </span>
      <input
        type={type}
        autoComplete="off"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={required ? "Required" : "Optional"}
        className="w-full rounded-md border border-slate-300 bg-slate-50 px-3 py-1.5 font-mono text-sm text-slate-800 placeholder-slate-400 focus:border-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-500"
      />
    </label>
  );
}
