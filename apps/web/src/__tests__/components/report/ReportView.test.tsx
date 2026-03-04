/**
 * @jest-environment jsdom
 */
import { render, screen } from "@testing-library/react";

import ReportView from "../../../components/report/ReportView";
import { SESSION_KEY } from "../../../hooks/useSession";
import type { BallotReport } from "../../../lib/types";

// Mock next/link to render plain <a> tags
jest.mock("next/link", () => {
  return ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  );
});

// Mock useReport hook
const mockRefetch = jest.fn();
const mockUseReport = jest.fn();
jest.mock("../../../hooks/useReport", () => ({
  useReport: (...args: unknown[]) => mockUseReport(...args),
}));

const REPORT_STUB: BallotReport = {
  session_id: "s-1",
  generated_at: "2026-01-15T00:00:00Z",
  election: { id: "FL-2026-GEN", name: "2026 Florida General", date: "2026-11-03", state: "FL" },
  precinct: { county: "Miami-Dade", district: null, precinct_id: null },
  user_priorities: ["housing", "education"],
  items: [
    {
      item_type: "measure",
      relevance_score: 9,
      relevance_reason: "Matches housing",
      matched_priorities: ["housing"],
      measure: {
        measure_id: "m-1",
        short_title: "Amendment 1",
        plain_english_summary: "Summary 1",
        what_yes_means: "Yes effect",
        what_no_means: "No effect",
        fiscal_impact: null,
        fiscal_impact_source: null,
        proponent_argument: "Pro arg",
        opponent_argument: "Con arg",
        proponent_source: "https://example.com/for",
        opponent_source: "https://example.com/against",
        topic_tags: ["housing"],
        data_completeness: "full",
        sources: [],
      },
    },
    {
      item_type: "measure",
      relevance_score: 5,
      relevance_reason: "Matches education",
      matched_priorities: ["education"],
      measure: {
        measure_id: "m-2",
        short_title: "Amendment 2",
        plain_english_summary: "Summary 2",
        what_yes_means: "Yes 2",
        what_no_means: "No 2",
        fiscal_impact: "$100M",
        fiscal_impact_source: "https://example.com/fiscal",
        proponent_argument: "Pro 2",
        opponent_argument: "Con 2",
        proponent_source: "https://example.com/for2",
        opponent_source: "https://example.com/against2",
        topic_tags: ["education"],
        data_completeness: "full",
        sources: [],
      },
    },
  ],
};

beforeEach(() => {
  jest.resetAllMocks();
  localStorage.clear();
});

describe("ReportView", () => {
  it("renders items in API order (no re-sorting)", () => {
    mockUseReport.mockReturnValue({
      report: REPORT_STUB,
      freshness: "fresh",
      isLoading: false,
      error: null,
      refetch: mockRefetch,
    });
    localStorage.setItem(SESSION_KEY, "s-1");

    render(<ReportView sessionId="s-1" />);

    const cards = screen.getAllByText(/Amendment \d/);
    expect(cards[0]).toHaveTextContent("Amendment 1");
    expect(cards[1]).toHaveTextContent("Amendment 2");
  });

  it("shows disclaimer banner for shared session", () => {
    mockUseReport.mockReturnValue({
      report: REPORT_STUB,
      freshness: "fresh",
      isLoading: false,
      error: null,
      refetch: mockRefetch,
    });
    // Different session in localStorage → shared
    localStorage.setItem(SESSION_KEY, "s-other");

    render(<ReportView sessionId="s-1" />);

    expect(
      screen.getByText(/personalized for priorities/),
    ).toBeInTheDocument();
  });
});
