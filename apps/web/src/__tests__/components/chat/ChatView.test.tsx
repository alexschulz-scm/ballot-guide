/**
 * @jest-environment jsdom
 */
import { act, fireEvent, render, screen } from "@testing-library/react";

import ChatView from "../../../components/chat/ChatView";
import type { BallotReport, OrchestratorEvent } from "../../../lib/types";

// Mock next/link to render plain <a> tags
jest.mock("next/link", () => {
  return ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  );
});

// Mock scrollIntoView
Element.prototype.scrollIntoView = jest.fn();

// Mock useSession
const mockUseSession = jest.fn();
jest.mock("../../../hooks/useSession", () => ({
  useSession: () => mockUseSession(),
}));

// Mock useSSEStream — use a stable mock + setter for event simulation
const stableSendMessage = jest.fn();
let simulateEvents: (events: OrchestratorEvent[]) => void;
let setMockStreaming: (v: boolean) => void;

jest.mock("../../../hooks/useSSEStream", () => ({
  useSSEStream: () => {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { useState } = require("react") as typeof import("react");
    const [events, setEvents] = useState<OrchestratorEvent[]>([]);
    const [isStreaming, setIsStreaming] = useState<boolean>(false);

    // Re-bind the implementation each render so it can call setIsStreaming
    stableSendMessage.mockImplementation(() => {
      setIsStreaming(true);
    });

    simulateEvents = (newEvents: OrchestratorEvent[]) => {
      setEvents(newEvents);
      setIsStreaming(false);
    };

    setMockStreaming = setIsStreaming;

    return {
      sendMessage: stableSendMessage,
      events,
      latestEvent: events.length > 0 ? events[events.length - 1] : null,
      isStreaming,
      streamError: null,
      clearEvents: jest.fn(),
    };
  },
}));

const MOCK_REPORT: BallotReport = {
  session_id: "s-1",
  generated_at: "2026-01-15T00:00:00Z",
  election: { id: "FL-2026-GEN", name: "2026 Florida General", date: "2026-11-03", state: "FL" },
  precinct: { county: "Miami-Dade", district: null, precinct_id: null },
  user_priorities: ["housing"],
  items: [
    {
      item_type: "measure",
      relevance_score: 9,
      relevance_reason: "Matches housing",
      matched_priorities: ["housing"],
      measure: {
        measure_id: "m-1",
        short_title: "Amendment 1",
        plain_english_summary: "Summary",
        what_yes_means: "Yes",
        what_no_means: "No",
        fiscal_impact: null,
        fiscal_impact_source: null,
        proponent_argument: "Pro",
        opponent_argument: "Con",
        proponent_source: "https://example.com/for",
        opponent_source: "https://example.com/against",
        topic_tags: ["housing"],
        data_completeness: "full",
        sources: [],
      },
    },
  ],
};

beforeEach(() => {
  jest.clearAllMocks();
  localStorage.clear();

  mockUseSession.mockReturnValue({
    sessionId: "s-1",
    session: {
      session_id: "s-1",
      created_at: "2026-01-15T00:00:00Z",
      updated_at: "2026-01-15T00:00:00Z",
      display_name: null,
      language: "en",
      status: "active",
      zip_code: null,
      priorities: [],
      has_report: false,
      election_name: null,
      message_count: 0,
    },
    isLoading: false,
    error: null,
  });
});

describe("ChatView", () => {
  it("shows chips after ballot_found event", () => {
    render(<ChatView />);

    // Chips not visible initially
    expect(screen.queryByText("See My Ballot Guide")).not.toBeInTheDocument();

    // Simulate ballot_found
    act(() => {
      simulateEvents([
        {
          event_type: "ballot_found",
          session_id: "s-1",
          timestamp: "2026-01-15T00:00:00Z",
          election_name: "2026 Florida General",
          item_count: 5,
          message: "Found your ballot",
        },
      ]);
    });

    expect(screen.getByText("See My Ballot Guide")).toBeInTheDocument();
  });

  it("hides chips after submit", () => {
    render(<ChatView />);

    // Show chips
    act(() => {
      simulateEvents([
        {
          event_type: "ballot_found",
          session_id: "s-1",
          timestamp: "2026-01-15T00:00:00Z",
          election_name: "2026 Florida General",
          item_count: 5,
          message: "Found your ballot",
        },
      ]);
    });

    // Type in input and send
    const input = screen.getByRole("textbox");
    fireEvent.change(input, { target: { value: "I care about housing" } });
    fireEvent.keyDown(input, { key: "Enter" });

    // Chips should be hidden after send
    expect(screen.queryByText("See My Ballot Guide")).not.toBeInTheDocument();
  });

  it("shows view report button after report_complete", () => {
    render(<ChatView />);

    act(() => {
      simulateEvents([
        {
          event_type: "report_complete",
          session_id: "s-1",
          timestamp: "2026-01-15T00:00:00Z",
          report: MOCK_REPORT,
        },
      ]);
    });

    expect(screen.getByText(/View Full Ballot Guide/)).toBeInTheDocument();
  });

  it("adds user message to thread on send", () => {
    render(<ChatView />);

    const input = screen.getByRole("textbox");
    fireEvent.change(input, { target: { value: "33101" } });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(screen.getByText("33101")).toBeInTheDocument();
    expect(stableSendMessage).toHaveBeenCalledWith("33101");
  });

  it("disables input while streaming", () => {
    render(<ChatView />);

    // Send a message to start streaming
    const input = screen.getByRole("textbox");
    fireEvent.change(input, { target: { value: "33101" } });
    fireEvent.keyDown(input, { key: "Enter" });

    // Input should be disabled during streaming
    expect(input).toBeDisabled();
  });
});
