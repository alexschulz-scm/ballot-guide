import { t } from "@/lib/i18n";
import type { CandidateAnalysis } from "@/lib/types";

interface Props {
  candidates: CandidateAnalysis[];
  priorities: string[];
}

export default function ComparisonTable({ candidates, priorities }: Props) {
  if (candidates.length < 2) return null;

  return (
    <div className="mt-4 overflow-x-auto">
      {/* Desktop: table layout */}
      <table className="hidden md:table w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-gray-200">
            <th className="text-left py-2 pr-4 font-semibold text-gray-600 w-1/5">
              Topic
            </th>
            {candidates.map((c) => (
              <th
                key={c.candidate_id}
                className="text-left py-2 px-3 font-semibold text-[#1A1A18]"
              >
                {c.name}
                {c.party && (
                  <span className="text-gray-500 font-normal ml-1">
                    ({c.party})
                  </span>
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {priorities.map((priority) => (
            <tr key={priority} className="border-b border-gray-100">
              <td className="py-3 pr-4 font-medium text-gray-600 capitalize align-top">
                {priority.replace("_", " ")}
              </td>
              {candidates.map((c) => (
                <td
                  key={c.candidate_id}
                  className="py-3 px-3 text-gray-800 align-top"
                >
                  {c.positions[priority] ??
                    t("report.no_position", { topic: priority })}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>

      {/* Mobile: stacked layout */}
      <div className="md:hidden space-y-4">
        {priorities.map((priority) => (
          <div
            key={priority}
            className="rounded-lg border border-gray-200 p-4"
          >
            <h4 className="font-semibold text-gray-600 capitalize mb-2">
              {priority.replace("_", " ")}
            </h4>
            <div className="space-y-3">
              {candidates.map((c) => (
                <div key={c.candidate_id}>
                  <p className="text-sm font-medium text-[#1A1A18]">
                    {c.name}
                    {c.party && (
                      <span className="text-gray-500 ml-1">({c.party})</span>
                    )}
                  </p>
                  <p className="text-sm text-gray-800 mt-0.5">
                    {c.positions[priority] ??
                      t("report.no_position", { topic: priority })}
                  </p>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
