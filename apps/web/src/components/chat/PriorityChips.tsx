"use client";

import { useState } from "react";

import { t } from "@/lib/i18n";

interface Props {
  onSubmit: (message: string) => void;
  visible: boolean;
}

const TAXONOMY_KEYS = [
  "housing",
  "education",
  "taxes",
  "healthcare",
  "environment",
  "public_safety",
  "economy",
  "voting_rights",
  "infrastructure",
  "senior_services",
] as const;

export default function PriorityChips({ onSubmit, visible }: Props) {
  const [selected, setSelected] = useState<string[]>([]);

  if (!visible) return null;

  function toggleChip(key: string) {
    setSelected((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key],
    );
  }

  function handleSubmit() {
    if (selected.length === 0) return;
    const labels = selected.map((k) => t(`priority_chips.${k}`));
    onSubmit(`I care about: ${labels.join(", ")}`);
  }

  return (
    <div className="px-4 py-3">
      <p className="mb-2 text-sm text-gray-600">
        {t("chat.priority_chips_prompt")}
      </p>
      <div className="flex flex-wrap gap-2 mb-3">
        {TAXONOMY_KEYS.map((key) => (
          <button
            key={key}
            type="button"
            onClick={() => toggleChip(key)}
            className={`rounded-full px-3 py-1.5 text-sm border transition-colors ${
              selected.includes(key)
                ? "bg-[var(--accent)] text-white border-[var(--accent)]"
                : "bg-white text-gray-700 border-gray-300 hover:border-gray-400"
            }`}
          >
            {t(`priority_chips.${key}`)}
          </button>
        ))}
      </div>
      <button
        type="button"
        onClick={handleSubmit}
        disabled={selected.length === 0}
        className="rounded-full bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {t("chat.send_chips_button")}
      </button>
    </div>
  );
}
