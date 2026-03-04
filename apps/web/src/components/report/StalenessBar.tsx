import { t } from "@/lib/i18n";

interface Props {
  freshness: "fresh" | "stale" | "very_stale";
  onRefresh: () => void;
}

export default function StalenessBar({ freshness, onRefresh }: Props) {
  if (freshness === "fresh") return null;

  const isStale = freshness === "stale";

  return (
    <div
      className={`rounded-md px-4 py-3 flex items-center justify-between ${
        isStale ? "bg-blue-50 border border-blue-200" : "bg-yellow-50 border border-yellow-300"
      }`}
      role="alert"
    >
      <p className={`text-sm ${isStale ? "text-blue-800" : "text-yellow-800"}`}>
        {isStale ? t("freshness.stale_message") : t("freshness.very_stale_message")}
      </p>
      <button
        onClick={onRefresh}
        className={`no-print ml-4 text-sm font-medium px-3 py-1 rounded ${
          isStale
            ? "bg-blue-100 text-blue-700 hover:bg-blue-200"
            : "bg-yellow-100 text-yellow-700 hover:bg-yellow-200"
        }`}
      >
        {isStale ? t("freshness.stale_button") : t("freshness.very_stale_button")}
      </button>
    </div>
  );
}
