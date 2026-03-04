/**
 * @jest-environment jsdom
 */
import { render, screen } from "@testing-library/react";

import CandidatePanel from "../../../components/report/CandidatePanel";
import type { CandidateAnalysis } from "../../../lib/types";

const CANDIDATE: CandidateAnalysis = {
  candidate_id: "c-1",
  name: "Jane Doe",
  party: "Independent",
  bio_summary: "A lifelong public servant.",
  positions: { housing: "Supports affordable housing programs." },
  top_donors: ["Donor X ($10,000)"],
  funding_total: "$100,000 raised",
  sources: [],
};

describe("CandidatePanel", () => {
  it("renders explicit no-position text for a missing topic", () => {
    render(
      <CandidatePanel
        candidate={CANDIDATE}
        priorities={["housing", "education"]}
      />,
    );
    expect(screen.getByText("No public statement found on education.")).toBeInTheDocument();
  });

  it("never silently omits a priority topic", () => {
    const priorities = ["housing", "education", "taxes"];
    render(<CandidatePanel candidate={CANDIDATE} priorities={priorities} />);

    // housing has a position, education and taxes do not
    expect(screen.getByText(/Supports affordable housing/)).toBeInTheDocument();
    expect(screen.getByText("No public statement found on education.")).toBeInTheDocument();
    expect(screen.getByText("No public statement found on taxes.")).toBeInTheDocument();
  });
});
