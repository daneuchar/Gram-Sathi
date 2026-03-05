const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function apiFetch<T>(
  path: string,
  params?: Record<string, string | number>,
  method: "GET" | "POST" = "GET"
): Promise<T> {
  const url = new URL(`${BASE_URL}${path}`);
  if (params && method === "GET") {
    for (const [key, value] of Object.entries(params)) {
      if (value !== "" && value !== undefined) {
        url.searchParams.set(key, String(value));
      }
    }
  }
  const res = await fetch(url.toString(), { method });
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const url = `${BASE_URL}${path}`;
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }
  return res.json();
}
