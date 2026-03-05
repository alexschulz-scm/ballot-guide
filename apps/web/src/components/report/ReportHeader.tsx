"use client";

import { useState } from "react";
import Link from "next/link";

import { t } from "@/lib/i18n";
import type { BallotReport } from "@/lib/types";
import StalenessBar from "./StalenessBar";

interface Props {
  report: BallotReport;
  freshness: "fresh" | "stale" | "very_stale";
  isShared: boolean;
  onRefresh: () => void;
}

export default function ReportHeader({ report, freshness, isShared, onRefresh }: Props) {
  const [copied, setCopied] = useState(false);

  const dateStr = new Date(report.generated_at).toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });

  function handleShare() {
    navigator.clipboard.writeText(window.location.href);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <header className="mb-6">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold text-[#1A1A18]">
          {t("report.title")}
        </h1>
        <div className="no-print flex gap-2">
          <Link
            href="/"
            className="text-sm text-[#1B4FD8] hover:underline"
          >
            {t("report.back_to_chat")}
          </Link>
          <button
            onClick={() => window.print()}
            className="text-sm text-[#1B4FD8] hover:underline ml-3"
          >
            {t("report.print")}
          </button>
          <button
            onClick={handleShare}
            className="text-sm text-[#1B4FD8] hover:underline ml-3"
          >
            {copied ? t("report.link_copied") : t("report.share")}
          </button>
        </div>
      </div>

      <div className="text-sm text-gray-600 mb-2">
        <p className="font-medium">{report.election.name}</p>
        <p>{t("report.generated_on", { date: dateStr })}</p>
        <p className="mt-1">
          Priorities: {report.user_priorities.join(", ")}
        </p>
      </div>

      {isShared && <SharedDisclaimer priorities={report.user_priorities} />}

      <StalenessBar freshness={freshness} onRefresh={onRefresh} />
    </header>
  );
}

function SharedDisclaimer({ priorities }: { priorities: string[] }) {
  return (
    <div className="rounded-md bg-blue-50 border border-blue-200 px-4 py-3 mb-4">
      <p className="text-sm text-blue-800">
        {t("shared_report.disclaimer", { priorities: priorities.join(", ") })}
      </p>
      <Link href="/" className="text-sm text-[#1B4FD8] underline mt-1 inline-block">
        {t("shared_report.create_own")}
      </Link>
    </div>
  );
}
