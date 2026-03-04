/**
 * @jest-environment jsdom
 */
import { render, screen } from "@testing-library/react";

import RaceCard from "../../../components/report/RaceCard";
import type { BallotReportItem, CandidateAnalysis, RaceAnalysis } from "../../../lib/types";

const CANDIDATE_A: CandidateAnalysis = {
  candidate_id: "c-1",
  name: "Alice Smith",
  party: "Independent",
  bio_summary: "Community organizer.",
  positions: { housing: "Supports rent control." },
  top_donors: ["Donor A ($5,000)"],
  funding_total: "$50,000 raised",
  sources: [],
};

const CANDIDATE_B: CandidateAnalysis = {
  candidate_id: "c-2",
  name: "Bob Jones",
  party: "Independent",
  bio_summary: "Business owner.",
  positions: { housing: "Opposes rent control." },
  top_donors: [],
  funding_total: null,
  sources: [],
};

function makeRaceItem(overrides?: Partial<RaceAnalysis>): BallotReportItem {
  return {
    item_type: "race",
    relevance_score: 7,
    relevance_reason: "Affects housing policy",
    matched_priorities: ["housing"],
    race: {
      race_id: "r-1",
      race_title: "State Senate District 1",
      race_type: "state_senate",
      candidates: [CANDIDATE_A, CANDIDATE_B],
      data_completeness: "full",
      sources: [],
      ...overrides,
    },
  };
}

describe("RaceCard", () => {
  it("renders a CandidatePanel for each candidate", () => {
    render(<RaceCard item={makeRaceItem()} priorities={["housing"]} />);
    expect(screen.getByText("Alice Smith")).toBeInTheDocument();
    expect(screen.getByText("Bob Jones")).toBeInTheDocument();
  });

  it("renders LimitedDataCard for limited data_completeness", () => {
    render(
      <RaceCard
        item={makeRaceItem({ data_completeness: "limited" })}
        priorities={["housing"]}
      />,
    );
    expect(screen.getByText(/Limited information available/)).toBeInTheDocument();
    expect(screen.queryByText("Alice Smith")).not.toBeInTheDocument();
  });
});
