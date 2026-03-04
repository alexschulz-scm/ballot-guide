import { t } from "@/lib/i18n";

const FL_ELECTIONS_URL = "https://dos.myflorida.com/elections/candidates-committees/";
const LWV_GUIDE_URL = "https://www.lwvfl.org/voters-guide/";

interface Props {
  title: string;
  candidateNames: string[];
}

export default function LimitedDataCard({ title, candidateNames }: Props) {
  return (
    <div className="ballot-card rounded-lg border border-amber-300 bg-amber-50 p-6 shadow-sm">
      <h3 className="text-lg font-semibold text-amber-900 mb-2">
        {title}
      </h3>
      <p className="text-sm text-amber-800 mb-3">
        {t("report.limited_data_title")}. This sometimes happens with local or
        judicial retention races.
      </p>
      {candidateNames.length > 0 && (
        <p className="text-sm text-amber-800 mb-4">
          Candidates: {candidateNames.join(", ")}
        </p>
      )}
      <div className="space-y-2">
        <a
          href={FL_ELECTIONS_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="block text-sm text-[#1B4FD8] underline"
        >
          View official candidate list (Florida Division of Elections)
        </a>
        <a
          href={LWV_GUIDE_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="block text-sm text-[#1B4FD8] underline"
        >
          Check the League of Women Voters guide
        </a>
      </div>
    </div>
  );
}
