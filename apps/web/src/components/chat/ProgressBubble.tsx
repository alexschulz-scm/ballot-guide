"use client";

import { t } from "@/lib/i18n";
import type { OrchestratorEvent } from "@/lib/types";

interface Props {
  latestEvent: OrchestratorEvent | null;
  isStreaming: boolean;
}

function getStatusLabel(event: OrchestratorEvent | null): string {
  if (!event) return t("chat.progress.starting");
  switch (event.event_type) {
    case "intake_complete":
      return t("chat.progress.found_ballot");
    case "ballot_found":
      return `${t("chat.progress.analyzing")} ${event.item_count} items...`;
    case "item_analyzed":
      return `${t("chat.progress.analyzing_item", { title: event.item_title })} (${event.items_complete}/${event.items_total})`;
    case "ranking_complete":
      return t("chat.progress.ranking");
    default:
      return t("chat.progress.working");
  }
}

export default function ProgressBubble({ latestEvent, isStreaming }: Props) {
  if (!isStreaming) return null;

  const label = getStatusLabel(latestEvent);

  return (
    <div className="flex justify-start mb-3">
      <div className="max-w-[80%] rounded-2xl rounded-bl-sm bg-gray-100 px-4 py-3 text-sm text-gray-700">
        <div className="flex items-center gap-2">
          <div className="h-2 w-2 animate-pulse rounded-full bg-[var(--accent)]" />
          <span>{label}</span>
        </div>
      </div>
    </div>
  );
}
