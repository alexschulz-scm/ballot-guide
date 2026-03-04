import { t } from "@/lib/i18n";
import type { BallotReportItem } from "@/lib/types";
import LimitedDataCard from "./LimitedDataCard";
import SourceList from "./SourceList";

interface Props {
  item: BallotReportItem;
  priorities: string[];
}

export default function MeasureCard({ item, priorities }: Props) {
  const measure = item.measure!;

  if (measure.data_completeness === "limited") {
    return <LimitedDataCard title={measure.short_title} candidateNames={[]} />;
  }

  return (
    <div className="ballot-card rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
      <Header title={measure.short_title} reason={item.relevance_reason} />
      <p className="text-gray-700 mb-4">{measure.plain_english_summary}</p>
      <Outcomes yesText={measure.what_yes_means} noText={measure.what_no_means} />
      <FiscalImpact text={measure.fiscal_impact} />
      <ForAgainst
        proponent={measure.proponent_argument}
        opponent={measure.opponent_argument}
      />
      <SourceList sources={measure.sources} />
    </div>
  );
}

function Header({ title, reason }: { title: string; reason: string }) {
  return (
    <div className="mb-4">
      <h3 className="text-xl font-semibold text-[#1A1A18]">{title}</h3>
      <p className="text-sm text-gray-500 mt-1">{reason}</p>
    </div>
  );
}

function Outcomes({ yesText, noText }: { yesText: string; noText: string }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
      <div className="rounded-md bg-gray-50 p-3">
        <h4 className="text-sm font-semibold text-gray-600 mb-1">
          {t("report.yes_means")}
        </h4>
        <p className="text-sm text-gray-700">{yesText}</p>
      </div>
      <div className="rounded-md bg-gray-50 p-3">
        <h4 className="text-sm font-semibold text-gray-600 mb-1">
          {t("report.no_means")}
        </h4>
        <p className="text-sm text-gray-700">{noText}</p>
      </div>
    </div>
  );
}

function FiscalImpact({ text }: { text: string | null }) {
  return (
    <div className="mb-4">
      <h4 className="text-sm font-semibold text-gray-600 mb-1">
        {t("report.fiscal_impact")}
      </h4>
      <p className="text-sm text-gray-700">
        {text ?? t("report.fiscal_not_published")}
      </p>
    </div>
  );
}

function ForAgainst({ proponent, opponent }: { proponent: string; opponent: string }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
      <div className="rounded-md border-l-4 border-emerald-400 bg-emerald-50 p-3">
        <h4 className="text-sm font-semibold text-gray-700 mb-1">
          {t("report.for_label")}
        </h4>
        <p className="text-sm text-gray-700">{proponent}</p>
      </div>
      <div className="rounded-md border-l-4 border-gray-300 bg-gray-50 p-3">
        <h4 className="text-sm font-semibold text-gray-700 mb-1">
          {t("report.against_label")}
        </h4>
        <p className="text-sm text-gray-700">{opponent}</p>
      </div>
    </div>
  );
}
