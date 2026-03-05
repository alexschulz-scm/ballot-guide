/**
 * @jest-environment jsdom
 */
import { render, screen } from "@testing-library/react";

import MeasureCard from "../../../components/report/MeasureCard";
import type { BallotReportItem, MeasureAnalysis, SourceCitation } from "../../../lib/types";

const SOURCE_STUB: SourceCitation = {
  name: "Ballotpedia",
  url: "https://ballotpedia.org/test",
  bias_rating: null,
  bias_source: null,
  bias_rating_url: null,
  fetched_at: "2026-01-01T00:00:00Z",
};

const MEASURE_STUB: MeasureAnalysis = {
  measure_id: "m-1",
  short_title: "Amendment 1: Housing Fund",
  plain_english_summary: "Creates a fund for affordable housing.",
  what_yes_means: "Fund is created.",
  what_no_means: "No fund.",
  fiscal_impact: "$500M over 10 years",
  fiscal_impact_source: "https://example.com/fiscal",
  proponent_argument: "Addresses the housing crisis.",
  opponent_argument: "Costs too much taxpayer money.",
  proponent_source: "https://example.com/for",
  opponent_source: "https://example.com/against",
  topic_tags: ["housing"],
  data_completeness: "full",
  sources: [SOURCE_STUB],
};

function makeItem(overrides?: Partial<MeasureAnalysis>): BallotReportItem {
  return {
    item_type: "measure",
    relevance_score: 8,
    relevance_reason: "Matches your interest in housing",
    matched_priorities: ["housing"],
    measure: { ...MEASURE_STUB, ...overrides },
  };
}

describe("MeasureCard", () => {
  it("renders both For and Against sections", () => {
    render(<MeasureCard item={makeItem()} priorities={["housing"]} />);
    expect(screen.getByText("Addresses the housing crisis.")).toBeInTheDocument();
    expect(screen.getByText("Costs too much taxpayer money.")).toBeInTheDocument();
  });

  it("renders LimitedDataCard for limited data_completeness", () => {
    render(
      <MeasureCard
        item={makeItem({ data_completeness: "limited" })}
        priorities={["housing"]}
      />,
    );
    expect(screen.getByText(/Limited information available/)).toBeInTheDocument();
    expect(screen.queryByText("Addresses the housing crisis.")).not.toBeInTheDocument();
  });

  it("renders fiscal not published when fiscal_impact is null", () => {
    render(
      <MeasureCard
        item={makeItem({ fiscal_impact: null })}
        priorities={["housing"]}
      />,
    );
    expect(screen.getByText("Fiscal impact not yet published.")).toBeInTheDocument();
  });

  it("renders all sources as links", () => {
    render(<MeasureCard item={makeItem()} priorities={["housing"]} />);
    const link = screen.getByRole("link", { name: "Ballotpedia" });
    expect(link).toHaveAttribute("href", "https://ballotpedia.org/test");
  });

  it("uses exact For and Against labels", () => {
    render(<MeasureCard item={makeItem()} priorities={["housing"]} />);
    expect(screen.getByText("For")).toBeInTheDocument();
    expect(screen.getByText("Against")).toBeInTheDocument();
    expect(screen.queryByText("Support")).not.toBeInTheDocument();
    expect(screen.queryByText("Oppose")).not.toBeInTheDocument();
  });
});
