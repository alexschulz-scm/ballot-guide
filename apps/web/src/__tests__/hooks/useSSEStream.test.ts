/**
 * @jest-environment jsdom
 */
import { act, renderHook, waitFor } from "@testing-library/react";

import { streamMessage } from "../../lib/api";
import type { OrchestratorEvent } from "../../lib/types";
import { useSSEStream } from "../../hooks/useSSEStream";

jest.mock("../../lib/api");

const mockedStreamMessage = streamMessage as jest.MockedFunction<typeof streamMessage>;

beforeEach(() => {
  jest.resetAllMocks();
});

const INTAKE_EVENT: OrchestratorEvent = {
  event_type: "intake_complete",
  session_id: "s-1",
  timestamp: "2026-01-01T00:00:00Z",
  zip_code: "33101",
  priorities: ["housing"],
  display_name: null,
};

const DONE_EVENT: OrchestratorEvent = {
  event_type: "done",
  session_id: "s-1",
  timestamp: "2026-01-01T00:00:01Z",
};

describe("useSSEStream", () => {
  it("has isStreaming false initially", () => {
    const { result } = renderHook(() => useSSEStream("s-1"));
    expect(result.current.isStreaming).toBe(false);
    expect(result.current.events).toEqual([]);
    expect(result.current.latestEvent).toBeNull();
  });

  it("sets isStreaming true after sendMessage", () => {
    mockedStreamMessage.mockReturnValue(new Promise(() => {})); // never resolves

    const { result } = renderHook(() => useSSEStream("s-1"));

    act(() => {
      result.current.sendMessage("hello");
    });

    expect(result.current.isStreaming).toBe(true);
  });

  it("sets isStreaming false after stream completes", async () => {
    mockedStreamMessage.mockResolvedValue(undefined);

    const { result } = renderHook(() => useSSEStream("s-1"));

    act(() => {
      result.current.sendMessage("hello");
    });

    await waitFor(() => expect(result.current.isStreaming).toBe(false));
  });

  it("accumulates events across the stream", async () => {
    mockedStreamMessage.mockImplementation(async (_id, _content, onEvent) => {
      onEvent(INTAKE_EVENT);
      onEvent(DONE_EVENT);
    });

    const { result } = renderHook(() => useSSEStream("s-1"));

    act(() => {
      result.current.sendMessage("33101");
    });

    await waitFor(() => expect(result.current.isStreaming).toBe(false));

    expect(result.current.events).toHaveLength(2);
    expect(result.current.events[0].event_type).toBe("intake_complete");
    expect(result.current.events[1].event_type).toBe("done");
  });

  it("updates latestEvent on each event", async () => {
    mockedStreamMessage.mockImplementation(async (_id, _content, onEvent) => {
      onEvent(INTAKE_EVENT);
      onEvent(DONE_EVENT);
    });

    const { result } = renderHook(() => useSSEStream("s-1"));

    act(() => {
      result.current.sendMessage("33101");
    });

    await waitFor(() => expect(result.current.isStreaming).toBe(false));

    expect(result.current.latestEvent?.event_type).toBe("done");
  });

  it("clears events when clearEvents is called", async () => {
    mockedStreamMessage.mockImplementation(async (_id, _content, onEvent) => {
      onEvent(INTAKE_EVENT);
    });

    const { result } = renderHook(() => useSSEStream("s-1"));

    act(() => {
      result.current.sendMessage("33101");
    });

    await waitFor(() => expect(result.current.isStreaming).toBe(false));
    expect(result.current.events).toHaveLength(1);

    act(() => {
      result.current.clearEvents();
    });

    expect(result.current.events).toEqual([]);
    expect(result.current.latestEvent).toBeNull();
  });

  it("sets streamError on fetch failure", async () => {
    mockedStreamMessage.mockRejectedValue(new Error("Network error"));

    const { result } = renderHook(() => useSSEStream("s-1"));

    act(() => {
      result.current.sendMessage("33101");
    });

    await waitFor(() => expect(result.current.isStreaming).toBe(false));

    expect(result.current.streamError).toBe("Connection lost. Please try again.");
  });
});
