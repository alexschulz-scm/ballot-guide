"use client";

import { useEffect, useState } from "react";

import { useReport } from "@/hooks/useReport";
import { SESSION_KEY } from "@/hooks/useSession";
import MeasureCard from "./MeasureCard";
import RaceCard from "./RaceCard";
import ReportHeader from "./ReportHeader";

interface Props {
  sessionId: string;
}

export default function ReportView({ sessionId }: Props) {
  const { report, freshness, isLoading, error, refetch } = useReport(sessionId);
  const [isShared, setIsShared] = useState(false);

  useEffect(() => {
    const storedId = localStorage.getItem(SESSION_KEY);
    setIsShared(storedId !== sessionId);
  }, [sessionId]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <p className="text-gray-500">Loading your ballot guide...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <p className="text-red-600">{error}</p>
      </div>
    );
  }

  if (!report || !freshness) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <p className="text-gray-500">Report not ready yet. Please check back soon.</p>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto px-4 py-8">
      <ReportHeader
        report={report}
        freshness={freshness}
        isShared={isShared}
        onRefresh={refetch}
      />
      <div className="space-y-6">
        {report.items.map((item) =>
          item.item_type === "measure" ? (
            <MeasureCard
              key={item.measure?.measure_id}
              item={item}
              priorities={report.user_priorities}
            />
          ) : (
            <RaceCard
              key={item.race?.race_id}
              item={item}
              priorities={report.user_priorities}
            />
          ),
        )}
      </div>
    </div>
  );
}
