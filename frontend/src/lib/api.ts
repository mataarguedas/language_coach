import type {
  Language,
  LanguageMeta,
  ShadowAnalysis,
  SynthesizeRequest,
  SynthesizeResponse,
  Voice,
} from "./types";

export interface AzureCredentials {
  key: string;
  region: string;
}

const BASE = import.meta.env.VITE_API_URL ?? "";

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, options);
  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`;
    try {
      const body = await resp.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // ignore parse error, use status text
    }
    throw new Error(detail);
  }
  return resp.json() as Promise<T>;
}

export async function fetchLanguages(): Promise<LanguageMeta[]> {
  return request<LanguageMeta[]>("/api/languages");
}

export async function fetchVoices(language: Language): Promise<Voice[]> {
  return request<Voice[]>(`/api/voices?language=${language}`);
}

export async function synthesize(
  body: SynthesizeRequest,
  fishKey: string,
  openAiKey: string,
): Promise<SynthesizeResponse> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "X-Fish-Key": fishKey,
  };
  if (openAiKey) {
    headers["X-OpenAI-Key"] = openAiKey;
  }
  return request<SynthesizeResponse>("/api/synthesize", {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
}

export interface AnalyzeShadowArgs {
  learner: Blob;
  learnerFilename?: string;
  targetCacheKey?: string;
  target?: Blob;
  targetFilename?: string;
  // Pronunciation-scoring inputs. Only forwarded when Azure creds are present;
  // omit them and the backend returns { prosody, pronunciation: null }.
  targetText?: string;
  language?: Language;
  azure?: AzureCredentials;
}

export async function analyzeShadow(
  args: AnalyzeShadowArgs,
): Promise<ShadowAnalysis> {
  const form = new FormData();
  form.append(
    "learner",
    args.learner,
    args.learnerFilename ?? "learner.webm",
  );
  if (args.targetCacheKey) {
    form.append("target_cache_key", args.targetCacheKey);
  } else if (args.target) {
    form.append("target", args.target, args.targetFilename ?? "target.wav");
  } else {
    throw new Error("analyzeShadow: provide targetCacheKey or target blob.");
  }

  const azureConfigured = !!(args.azure?.key && args.azure?.region);
  const headers: Record<string, string> = {};
  if (azureConfigured) {
    headers["X-Azure-Speech-Key"] = args.azure!.key;
    headers["X-Azure-Speech-Region"] = args.azure!.region;
    // Backend requires target_text + language alongside the Azure headers
    // when pronunciation is being requested. Without them it 422s.
    if (args.targetText) form.append("target_text", args.targetText);
    if (args.language) form.append("language", args.language);
  }

  return request<ShadowAnalysis>("/api/shadow/analyze", {
    method: "POST",
    headers,
    body: form,
  });
}
