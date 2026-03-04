"use client";

import { useEffect, useState } from "react";

import { listElections } from "@/lib/api";
import { t } from "@/lib/i18n";
import type { ElectionListItem } from "@/lib/types";

interface Props {
  selectedId: string | null;
  onChange: (electionId: string | null) => void;
  disabled?: boolean;
}

export default function ElectionSelector({ selectedId, onChange, disabled }: Props) {
  const [elections, setElections] = useState<ElectionListItem[]>([]);

  useEffect(() => {
    listElections().then(setElections).catch(() => {});
  }, []);

  if (elections.length === 0) return null;

  return (
    <select
      value={selectedId ?? ""}
      onChange={(e) => onChange(e.target.value || null)}
      disabled={disabled}
      className="rounded border border-gray-300 bg-white px-2 py-1 text-xs text-[var(--foreground)] focus:border-[var(--accent)] focus:outline-none"
      aria-label={t("header.election_label")}
    >
      {elections.map((e) => (
        <option key={e.id} value={e.id}>
          {e.name}
          {e.is_historical ? ` ${t("header.historical_suffix")}` : ""}
        </option>
      ))}
    </select>
  );
}
