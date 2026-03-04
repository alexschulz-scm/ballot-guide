"use client";

import { useCallback, useRef, useState } from "react";

import { streamMessage } from "@/lib/api";
import type { OrchestratorEvent } from "@/lib/types";

export function useSSEStream(sessionId: string | null) {
  const [events, setEvents] = useState<OrchestratorEvent[]>([]);
  const [latestEvent, setLatestEvent] = useState<OrchestratorEvent | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamError, setStreamError] = useState<string | null>(null);
  const streamingRef = useRef(false);

  const clearEvents = useCallback(() => {
    setEvents([]);
    setLatestEvent(null);
    setStreamError(null);
  }, []);

  const sendMessage = useCallback(
    (content: string) => {
      if (!sessionId || streamingRef.current) return;

      clearEvents();
      setIsStreaming(true);
      streamingRef.current = true;

      streamMessage(sessionId, content, (event) => {
        setEvents((prev) => [...prev, event]);
        setLatestEvent(event);
      })
        .then(() => {
          setIsStreaming(false);
          streamingRef.current = false;
        })
        .catch(() => {
          setStreamError("Connection lost. Please try again.");
          setIsStreaming(false);
          streamingRef.current = false;
        });
    },
    [sessionId, clearEvents],
  );

  return { sendMessage, events, latestEvent, isStreaming, streamError, clearEvents };
}
