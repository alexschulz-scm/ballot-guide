import { t } from "@/lib/i18n";

import ElectionSelector from "./ElectionSelector";

interface Props {
  selectedElectionId: string | null;
  onElectionChange: (id: string | null) => void;
  disabled?: boolean;
}

export default function Header({ selectedElectionId, onElectionChange, disabled }: Props) {
  return (
    <header className="flex items-center justify-between border-b border-gray-200 bg-white px-4 py-3 no-print">
      <div>
        <h1 className="text-lg font-semibold text-[var(--foreground)]">
          {t("header.title")}
        </h1>
        <p className="text-xs text-gray-500">
          {t("header.subtitle")}
        </p>
      </div>
      <ElectionSelector
        selectedId={selectedElectionId}
        onChange={onElectionChange}
        disabled={disabled}
      />
    </header>
  );
}
