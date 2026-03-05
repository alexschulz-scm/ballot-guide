import { createSession, getSession, getReport, streamMessage } from "../../lib/api";
import type { OrchestratorEvent, SessionMetadata, ReportResponse } from "../../lib/types";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const SESSION_STUB: SessionMetadata = {
  session_id: "s-123",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  display_name: null,
  language: "en",
  status: "active",
  zip_code: null,
  priorities: [],
  has_report: false,
  election_name: null,
  election_id: null,
  message_count: 0,
};

const REPORT_STUB: ReportResponse = {
  session_id: "s-123",
  report: {
    session_id: "s-123",
    generated_at: "2026-01-01T00:00:00Z",
    election: { id: "FL-2026-GEN", name: "Test", date: "2026-11-03", state: "FL" },
    precinct: { county: "Miami-Dade", district: null, precinct_id: null },
    user_priorities: ["housing"],
    items: [],
  },
  generated_at: "2026-01-01T00:00:00Z",
  data_freshness: "fresh",
  display_name: null,
  priorities: ["housing"],
};

function mockFetchJson(status: number, body: unknown): void {
  global.fetch = jest.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  });
}

function mockFetchStream(chunks: string[]): void {
  let index = 0;
  const encoder = new TextEncoder();
  const reader = {
    read: jest.fn().mockImplementation(() => {
      if (index < chunks.length) {
        return Promise.resolve({ done: false, value: encoder.encode(chunks[index++]) });
      }
      return Promise.resolve({ done: true, value: undefined });
    }),
  };
  global.fetch = jest.fn().mockResolvedValue({
    ok: true,
    status: 200,
    body: { getReader: () => reader },
  });
}

afterEach(() => {
  jest.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// createSession
// ---------------------------------------------------------------------------

describe("createSession", () => {
  it("sends POST and returns session metadata", async () => {
    mockFetchJson(201, SESSION_STUB);
    const result = await createSession();
    expect(result.session_id).toBe("s-123");
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/v1/session",
      expect.objectContaining({ method: "POST" }),
    );
  });
});

// ---------------------------------------------------------------------------
// getSession
// ---------------------------------------------------------------------------

describe("getSession", () => {
  it("returns metadata on 200", async () => {
    mockFetchJson(200, SESSION_STUB);
    const result = await getSession("s-123");
    expect(result).not.toBeNull();
    expect(result!.session_id).toBe("s-123");
  });

  it("returns null on 404", async () => {
    mockFetchJson(404, { error_code: "NOT_FOUND", message: "not found" });
    const result = await getSession("missing");
    expect(result).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// getReport
// ---------------------------------------------------------------------------

describe("getReport", () => {
  it("returns report on 200", async () => {
    mockFetchJson(200, REPORT_STUB);
    const result = await getReport("s-123");
    expect(result).not.toBeNull();
    expect(result!.session_id).toBe("s-123");
  });

  it("returns null on 404", async () => {
    mockFetchJson(404, { error_code: "NOT_FOUND", message: "not found" });
    const result = await getReport("missing");
    expect(result).toBeNull();
  });

  it("returns null on 202 (report still processing)", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      status: 202,
      json: () => Promise.resolve({ status: "processing" }),
    });
    const result = await getReport("s-123");
    expect(result).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// streamMessage
// ---------------------------------------------------------------------------

describe("streamMessage", () => {
  it("calls onEvent for each SSE event in the stream", async () => {
    const event1: OrchestratorEvent = {
      event_type: "intake_complete",
      session_id: "s-1",
      timestamp: "2026-01-01T00:00:00Z",
      zip_code: "33101",
      priorities: ["housing"],
      display_name: null,
    };
    const event2: OrchestratorEvent = {
      event_type: "done",
      session_id: "s-1",
      timestamp: "2026-01-01T00:00:01Z",
    };
    mockFetchStream([
      `data: ${JSON.stringify(event1)}\n\ndata: ${JSON.stringify(event2)}\n\n`,
    ]);

    const events: OrchestratorEvent[] = [];
    await streamMessage("s-1", "33101, housing", (e) => events.push(e));

    expect(events).toHaveLength(2);
    expect(events[0].event_type).toBe("intake_complete");
    expect(events[1].event_type).toBe("done");
  });

  it("handles JSON events split across two chunks", async () => {
    const event: OrchestratorEvent = {
      event_type: "ballot_found",
      session_id: "s-1",
      timestamp: "2026-01-01T00:00:00Z",
      election_name: "2026 Florida General",
      item_count: 10,
      message: "Found your ballot",
    };
    const full = `data: ${JSON.stringify(event)}\n\n`;
    // Split in the middle of the JSON payload
    const splitPoint = Math.floor(full.length / 2);
    const chunk1 = full.slice(0, splitPoint);
    const chunk2 = full.slice(splitPoint);
    mockFetchStream([chunk1, chunk2]);

    const events: OrchestratorEvent[] = [];
    await streamMessage("s-1", "hello", (e) => events.push(e));

    expect(events).toHaveLength(1);
    expect(events[0].event_type).toBe("ballot_found");
    expect((events[0] as { item_count: number }).item_count).toBe(10);
  });
});
