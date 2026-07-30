const FISH_KEY = "pc_fish_key";
const OPENAI_KEY = "pc_openai_key";
const AZURE_KEY = "pc_azure_key";
const AZURE_REGION = "pc_azure_region";

// BYOK: keys live in sessionStorage only, so they clear when the tab closes.
// Never persisted to disk, never sent anywhere except as per-request headers.

export function getFishKey(): string {
  return sessionStorage.getItem(FISH_KEY) ?? "";
}

export function getOpenAiKey(): string {
  return sessionStorage.getItem(OPENAI_KEY) ?? "";
}

export function getAzureKey(): string {
  return sessionStorage.getItem(AZURE_KEY) ?? "";
}

export function getAzureRegion(): string {
  return sessionStorage.getItem(AZURE_REGION) ?? "";
}

export function setFishKey(key: string): void {
  if (key) {
    sessionStorage.setItem(FISH_KEY, key);
  } else {
    sessionStorage.removeItem(FISH_KEY);
  }
}

export function setOpenAiKey(key: string): void {
  if (key) {
    sessionStorage.setItem(OPENAI_KEY, key);
  } else {
    sessionStorage.removeItem(OPENAI_KEY);
  }
}

export function setAzureKey(key: string): void {
  if (key) {
    sessionStorage.setItem(AZURE_KEY, key);
  } else {
    sessionStorage.removeItem(AZURE_KEY);
  }
}

export function setAzureRegion(region: string): void {
  if (region) {
    sessionStorage.setItem(AZURE_REGION, region);
  } else {
    sessionStorage.removeItem(AZURE_REGION);
  }
}

export function clearKeys(): void {
  sessionStorage.removeItem(FISH_KEY);
  sessionStorage.removeItem(OPENAI_KEY);
  sessionStorage.removeItem(AZURE_KEY);
  sessionStorage.removeItem(AZURE_REGION);
}
