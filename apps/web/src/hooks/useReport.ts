"use client";

import { useCallback, useEffect, useState } from "react";

import { getReport } from "@/lib/api";
import type { BallotReport } from "@/lib/types";

export function useReport(sessionId: string | null) {
  const [report, setReport] = useState<BallotReport | null>(null);
  const [freshness, setFreshness] = useState<"fresh" | "stale" | "very_stale" | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fetchCount, setFetchCount] = useState(0);

  const fetchReport = useCallback(async (id: string) => {
    setIsLoading(true);
    setError(null);
    try {
      const result = await getReport(id);
      if (result) {
        setReport(result.report);
        setFreshness(result.data_freshness);
      } else {
        setReport(null);
        setFreshness(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load report");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (sessionId) {
      fetchReport(sessionId);
    }
  }, [sessionId, fetchCount, fetchReport]);

  const refetch = useCallback(() => {
    setFetchCount((c) => c + 1);
  }, []);

  return { report, freshness, isLoading, error, refetch };
}
