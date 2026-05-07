const DEFAULT_API_BASE = "http://127.0.0.1:8000";
const API_BASE_KEY = "aria_api_base";
const API_KEY_KEY = "aria_api_key";

export function getApiBase() {
  const configured = process.env.NEXT_PUBLIC_ARIA_API_BASE;
  if (configured) return configured.replace(/\/$/, "");
  if (typeof window !== "undefined") {
    const saved = window.localStorage.getItem(API_BASE_KEY);
    if (saved) return saved.replace(/\/$/, "");
    return window.location.origin;
  }
  return DEFAULT_API_BASE;
}

export function getApiKey() {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem(API_KEY_KEY) || "";
}

export function setApiKey(apiKey: string) {
  if (typeof window === "undefined") return;
  if (!apiKey) {
    window.localStorage.removeItem(API_KEY_KEY);
    return;
  }
  window.localStorage.setItem(API_KEY_KEY, apiKey);
}

export function clearApiKey() {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(API_KEY_KEY);
}

export function setApiBase(apiBase: string) {
  if (typeof window === "undefined") return;
  if (!apiBase) {
    window.localStorage.removeItem(API_BASE_KEY);
    return;
  }
  window.localStorage.setItem(API_BASE_KEY, apiBase.replace(/\/$/, ""));
}

export function getAuthHeaders(): HeadersInit {
  const apiKey = getApiKey();
  return apiKey ? { Authorization: `Bearer ${apiKey}` } : {};
}

export function apiUrl(path: string) {
  return `${getApiBase()}${path}`;
}

export function wsUrl(path: string) {
  const base = getApiBase();
  const url = new URL(path, base);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  return url.toString();
}
