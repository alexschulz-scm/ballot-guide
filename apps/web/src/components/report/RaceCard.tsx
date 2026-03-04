import type { BallotReportItem } from "@/lib/types";
import CandidatePanel from "./CandidatePanel";
import LimitedDataCard from "./LimitedDataCard";

interface Props {
  item: BallotReportItem;
  priorities: string[];
}

export default function RaceCard({ item, priorities }: Props) {
  const race = item.race!;

  if (race.data_completeness === "limited") {
    return (
      <LimitedDataCard
        title={race.race_title}
        candidateNames={race.candidates.map((c) => c.name)}
      />
    );
  }

  return (
    <div className="ballot-card rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
      <div className="mb-4">
        <h3 className="text-xl font-semibold text-[#1A1A18]">{race.race_title}</h3>
        <p className="text-sm text-gray-500 mt-1">{item.relevance_reason}</p>
      </div>
      <div className="flex flex-col md:flex-row gap-4">
        {race.candidates.map((candidate) => (
          <CandidatePanel
            key={candidate.candidate_id}
            candidate={candidate}
            priorities={priorities}
          />
        ))}
      </div>
    </div>
  );
}
