import type { ElectionListItem, OrchestratorEvent, ReportResponse, SessionMetadata } from "./types";

const BASE = "/api/v1";

// ---------------------------------------------------------------------------
// Session endpoints
// ---------------------------------------------------------------------------

export async function listElections(): Promise<ElectionListItem[]> {
  const res = await fetch(`${BASE}/elections`);
  if (!res.ok) {
    throw new Error(`Failed to list elections: ${res.status}`);
  }
  return (await res.json()) as ElectionListItem[];
}

export async function createSession(
  displayName?: string,
  electionId?: string,
): Promise<SessionMetadata> {
  const res = await fetch(`${BASE}/session`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      display_name: displayName ?? null,
      language: "en",
      election_id: electionId ?? null,
    }),
  });
  if (!res.ok) {
    throw new Error(`Failed to create session: ${res.status}`);
  }
  return (await res.json()) as SessionMetadata;
}

export async function getSession(
  sessionId: string,
): Promise<SessionMetadata | null> {
  const res = await fetch(`${BASE}/session/${sessionId}`);
  if (res.status === 404) return null;
  if (!res.ok) {
    throw new Error(`Failed to get session: ${res.status}`);
  }
  return (await res.json()) as SessionMetadata;
}

// ---------------------------------------------------------------------------
// Report endpoint
// ---------------------------------------------------------------------------

export async function getReport(
  sessionId: string,
): Promise<ReportResponse | null> {
  const res = await fetch(`${BASE}/session/${sessionId}/report`);
  if (res.status === 404 || res.status === 202) return null;
  if (!res.ok) {
    throw new Error(`Failed to get report: ${res.status}`);
  }
  return (await res.json()) as ReportResponse;
}

// ---------------------------------------------------------------------------
// SSE streaming — fetch + ReadableStream (POST endpoint, not EventSource)
// ---------------------------------------------------------------------------

export async function streamMessage(
  sessionId: string,
  content: string,
  onEvent: (event: OrchestratorEvent) => void,
): Promise<void> {
  const res = await fetch(`${BASE}/session/${sessionId}/message`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });

  if (!res.ok) {
    throw new Error(`Failed to send message: ${res.status}`);
  }

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      try {
        const event = JSON.parse(line.slice(6)) as OrchestratorEvent;
        onEvent(event);
      } catch {
        // skip malformed JSON lines
      }
    }
  }

  // flush any remaining data in buffer
  if (buffer.startsWith("data: ")) {
    try {
      const event = JSON.parse(buffer.slice(6)) as OrchestratorEvent;
      onEvent(event);
    } catch {
      // skip malformed JSON
    }
  }
}
