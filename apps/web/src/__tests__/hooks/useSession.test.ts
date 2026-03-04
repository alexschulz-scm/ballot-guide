/**
 * @jest-environment jsdom
 */
import { renderHook, waitFor } from "@testing-library/react";

import { createSession, getSession } from "../../lib/api";
import type { SessionMetadata } from "../../lib/types";
import { SESSION_KEY, useSession } from "../../hooks/useSession";

jest.mock("../../lib/api");

const mockedCreateSession = createSession as jest.MockedFunction<typeof createSession>;
const mockedGetSession = getSession as jest.MockedFunction<typeof getSession>;

const SESSION_STUB: SessionMetadata = {
  session_id: "s-new",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  display_name: null,
  language: "en",
  status: "active",
  zip_code: null,
  priorities: [],
  has_report: false,
  election_name: null,
  message_count: 0,
};

beforeEach(() => {
  localStorage.clear();
  jest.resetAllMocks();
});

describe("useSession", () => {
  it("creates a new session when no localStorage key exists", async () => {
    mockedCreateSession.mockResolvedValue(SESSION_STUB);

    const { result } = renderHook(() => useSession());

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(mockedCreateSession).toHaveBeenCalledTimes(1);
    expect(result.current.sessionId).toBe("s-new");
    expect(result.current.session).toEqual(SESSION_STUB);
    expect(result.current.error).toBeNull();
  });

  it("stores session_id in localStorage after create", async () => {
    mockedCreateSession.mockResolvedValue(SESSION_STUB);

    const { result } = renderHook(() => useSession());

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(localStorage.getItem(SESSION_KEY)).toBe("s-new");
  });

  it("restores an existing session from localStorage", async () => {
    const existing: SessionMetadata = { ...SESSION_STUB, session_id: "s-existing" };
    localStorage.setItem(SESSION_KEY, "s-existing");
    mockedGetSession.mockResolvedValue(existing);

    const { result } = renderHook(() => useSession());

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(mockedGetSession).toHaveBeenCalledWith("s-existing");
    expect(mockedCreateSession).not.toHaveBeenCalled();
    expect(result.current.sessionId).toBe("s-existing");
    expect(result.current.session).toEqual(existing);
  });

  it("clears localStorage and creates new session on 404", async () => {
    localStorage.setItem(SESSION_KEY, "s-gone");
    mockedGetSession.mockResolvedValue(null);
    mockedCreateSession.mockResolvedValue(SESSION_STUB);

    const { result } = renderHook(() => useSession());

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(mockedGetSession).toHaveBeenCalledWith("s-gone");
    expect(mockedCreateSession).toHaveBeenCalledTimes(1);
    expect(result.current.sessionId).toBe("s-new");
    expect(localStorage.getItem(SESSION_KEY)).toBe("s-new");
  });
});
