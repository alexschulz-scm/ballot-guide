/**
 * @jest-environment jsdom
 */
import { renderHook, waitFor, act } from "@testing-library/react";

import { getReport } from "../../lib/api";
import type { ReportResponse } from "../../lib/types";
import { useReport } from "../../hooks/useReport";

jest.mock("../../lib/api");

const mockedGetReport = getReport as jest.MockedFunction<typeof getReport>;

const REPORT_STUB: ReportResponse = {
  session_id: "s-1",
  report: {
    session_id: "s-1",
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

beforeEach(() => {
  jest.resetAllMocks();
});

describe("useReport", () => {
  it("fetches report on mount when sessionId is provided", async () => {
    mockedGetReport.mockResolvedValue(REPORT_STUB);

    const { result } = renderHook(() => useReport("s-1"));

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(mockedGetReport).toHaveBeenCalledWith("s-1");
    expect(result.current.report).toEqual(REPORT_STUB.report);
    expect(result.current.freshness).toBe("fresh");
    expect(result.current.error).toBeNull();
  });

  it("returns null when report is not ready", async () => {
    mockedGetReport.mockResolvedValue(null);

    const { result } = renderHook(() => useReport("s-1"));

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.report).toBeNull();
    expect(result.current.freshness).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it("refetch triggers a new fetch", async () => {
    mockedGetReport.mockResolvedValue(REPORT_STUB);

    const { result } = renderHook(() => useReport("s-1"));

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(mockedGetReport).toHaveBeenCalledTimes(1);

    act(() => {
      result.current.refetch();
    });

    await waitFor(() => expect(mockedGetReport).toHaveBeenCalledTimes(2));
  });
});
