"use client";

import { useCallback, useEffect, useState } from "react";

import { createSession, getSession } from "@/lib/api";
import type { SessionMetadata } from "@/lib/types";

export const SESSION_KEY = "ballot_guide_session_id";
const ELECTION_KEY = "ballot_guide_election_id";

export function useSession() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [session, setSession] = useState<SessionMetadata | null>(null);
  const [selectedElectionId, setSelectedElectionId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const initSession = useCallback(async (electionId?: string | null) => {
    setIsLoading(true);
    setError(null);

    try {
      const storedId = localStorage.getItem(SESSION_KEY);
      const storedElection = localStorage.getItem(ELECTION_KEY);

      // Reuse existing session if election hasn't changed
      if (storedId && electionId === undefined) {
        const existing = await getSession(storedId);
        if (existing) {
          setSessionId(existing.session_id);
          setSession(existing);
          setSelectedElectionId(storedElection);
          setIsLoading(false);
          return;
        }
        localStorage.removeItem(SESSION_KEY);
      }

      // Create new session with optional election_id
      const eid = electionId ?? storedElection ?? undefined;
      const created = await createSession(undefined, eid);
      localStorage.setItem(SESSION_KEY, created.session_id);
      if (eid) {
        localStorage.setItem(ELECTION_KEY, eid);
      } else {
        localStorage.removeItem(ELECTION_KEY);
      }
      setSessionId(created.session_id);
      setSession(created);
      setSelectedElectionId(eid ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to initialize session");
    } finally {
      setIsLoading(false);
    }
  }, []);

  const switchElection = useCallback(
    (electionId: string | null) => {
      // Clear current session and start fresh with new election
      localStorage.removeItem(SESSION_KEY);
      setSelectedElectionId(electionId);
      initSession(electionId);
    },
    [initSession],
  );

  useEffect(() => {
    initSession();
  }, [initSession]);

  return { sessionId, session, isLoading, error, selectedElectionId, switchElection };
}
