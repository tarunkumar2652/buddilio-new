// Reads Buddy's SSE stream. fetch (not EventSource) because the member call needs an Authorization header.
export async function streamAi(path, body, onDelta) {
  const token = localStorage.getItem("bud_token");
  const res = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api${path}`, {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const j = await res.json().catch(() => ({}));
    throw new Error(j.detail || "Buddy is unavailable right now. Please try again.");
  }
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "", acc = "", failure = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const frames = buf.split("\n\n");
    buf = frames.pop();
    for (const f of frames) {
      const line = f.split("\n").find((l) => l.startsWith("data: "));
      if (!line) continue;
      const ev = JSON.parse(line.slice(6));
      if (ev.delta) { acc += ev.delta; onDelta?.(acc); }
      if (ev.error) failure = ev.error;
    }
  }
  if (failure && !acc.trim()) throw new Error(failure);
  return acc.trim();
}

export const newAiSession = () =>
  window.crypto?.randomUUID?.() || `s-${Date.now()}-${Math.random().toString(16).slice(2)}`;

export const GUEST_QA_KEY = "bud_guest_ai_qa";
