import { t } from "@/lib/i18n";
import type { SourceCitation } from "@/lib/types";

interface Props {
  sources: SourceCitation[];
}

export default function SourceList({ sources }: Props) {
  if (sources.length === 0) return null;

  return (
    <div className="mt-4">
      <h4 className="text-sm font-semibold text-gray-600 mb-1">
        {t("report.sources_label")}
      </h4>
      <ul className="list-none space-y-1">
        {sources.map((source) => (
          <li key={source.url} className="text-sm">
            <a
              href={source.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[#1B4FD8] underline"
            >
              {source.name}
            </a>
            {source.bias_rating && (
              <span className="text-gray-500 ml-1">({source.bias_rating})</span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
