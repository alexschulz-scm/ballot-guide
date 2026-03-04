import { t } from "@/lib/i18n";
import type { CandidateAnalysis } from "@/lib/types";
import SourceList from "./SourceList";

interface Props {
  candidate: CandidateAnalysis;
  priorities: string[];
}

export default function CandidatePanel({ candidate, priorities }: Props) {
  return (
    <div className="flex-1 rounded-lg border border-gray-200 bg-white p-5">
      <div className="mb-3">
        <h4 className="text-lg font-semibold text-[#1A1A18]">{candidate.name}</h4>
        {candidate.party && (
          <span className="text-sm text-gray-500">{candidate.party}</span>
        )}
      </div>

      {candidate.bio_summary && (
        <p className="text-sm text-gray-700 mb-3">{candidate.bio_summary}</p>
      )}

      <div className="mb-3 space-y-2">
        {priorities.map((priority) => (
          <div key={priority} className="text-sm">
            <span className="font-medium text-gray-600 capitalize">
              {priority.replace("_", " ")}:
            </span>{" "}
            <span className="text-gray-800">
              {candidate.positions[priority] ??
                t("report.no_position", { topic: priority })}
            </span>
          </div>
        ))}
      </div>

      {(candidate.funding_total || candidate.top_donors.length > 0) && (
        <div className="text-sm text-gray-600 mb-2">
          {candidate.funding_total && (
            <p className="font-medium">{candidate.funding_total}</p>
          )}
          {candidate.top_donors.length > 0 && (
            <p>Top donors: {candidate.top_donors.join(", ")}</p>
          )}
        </div>
      )}

      <SourceList sources={candidate.sources} />
    </div>
  );
}
