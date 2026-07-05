/**
 * Shared client for talking to the local Kinthic gateway (silex/api/server.py).
 *
 * The gateway is loopback-only and gated behind a locally-generated API key
 * (see RuntimeSettingsStore.ensure_web_api_key). `kinthic web` injects both
 * NEXT_PUBLIC_KINTHIC_API_BASE and NEXT_PUBLIC_KINTHIC_API_KEY into the dev
 * server's environment automatically, so this normally requires no manual
 * configuration.
 */

export const API_BASE =
  process.env.NEXT_PUBLIC_KINTHIC_API_BASE || "http://127.0.0.1:8000";

const API_KEY = process.env.NEXT_PUBLIC_KINTHIC_API_KEY || "";

export function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers || {});
  if (API_KEY) {
    headers.set("X-Kinthic-Api-Key", API_KEY);
  }
  return fetch(`${API_BASE}${path}`, { ...init, headers });
}

export function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}
