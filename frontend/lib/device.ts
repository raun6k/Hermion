// Stable per-browser device id; the backend allows one live session per device (docs/api.md).
const KEY = "hermion.device_id";

export function getDeviceId(): string {
  try {
    const existing = localStorage.getItem(KEY);
    if (existing) return existing;
    const id = crypto.randomUUID();
    localStorage.setItem(KEY, id);
    return id;
  } catch {
    return crypto.randomUUID();
  }
}
