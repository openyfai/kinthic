const DEFAULT_API_BASE = "http://127.0.0.1:8000";

export function getApiBase() {
  const configured = process.env.NEXT_PUBLIC_ARIA_API_BASE;
  if (configured) return configured.replace(/\/$/, "");
  if (typeof window !== "undefined") return window.location.origin;
  return DEFAULT_API_BASE;
}

export function getApiKey() {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem("aria_api_key") || "";
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

  const apiKey = getApiKey();
  if (apiKey) url.searchParams.set("token", apiKey);
  return url.toString();
}
