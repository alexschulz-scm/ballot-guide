"use client";

import { useEffect, useRef, useState } from "react";

import { t } from "@/lib/i18n";
import type { BallotReport } from "@/lib/types";
import { useSession } from "@/hooks/useSession";
import { useSSEStream } from "@/hooks/useSSEStream";

import Header from "../shared/Header";
import InputBar from "./InputBar";
import MessageThread from "./MessageThread";
import PriorityChips from "./PriorityChips";

interface Message {
  role: "user" | "assistant";
  content: string;
}

function buildReportSummary(report: BallotReport): string {
  const top3 = report.items.slice(0, 3);
  const intro = `Your ballot has ${report.items.length} items. Based on your priorities, here's what stands out:\n\n`;
  const items = top3
    .map((item) => {
      const title =
        item.measure?.short_title ?? item.race?.race_title ?? "Unknown";
      return `**${title}** — ${item.relevance_reason}`;
    })
    .join("\n\n");
  return (
    intro +
    items +
    `\n\nWant to go deeper on any of these, or view your full ballot guide?`
  );
}

export default function ChatView() {
  const { sessionId, session, isLoading, selectedElectionId, switchElection } = useSession();
  const { sendMessage, events, latestEvent, isStreaming } =
    useSSEStream(sessionId);

  const [messages, setMessages] = useState<Message[]>([]);
  const [showChips, setShowChips] = useState(false);
  const [showViewReport, setShowViewReport] = useState(false);
  const welcomeSent = useRef(false);
  const processedEventsCount = useRef(0);

  // Welcome message on mount or session restore
  useEffect(() => {
    if (!session || welcomeSent.current) return;
    welcomeSent.current = true;

    if (session.has_report) {
      const date = new Date(session.updated_at).toLocaleDateString();
      setMessages([
        {
          role: "assistant",
          content: t("chat.welcome_returning", { date }),
        },
      ]);
      setShowViewReport(true);
    } else {
      setMessages([{ role: "assistant", content: t("chat.welcome") }]);
    }
  }, [session]);

  // React to SSE events — process ALL new events, not just the last
  useEffect(() => {
    const newEvents = events.slice(processedEventsCount.current);
    if (newEvents.length === 0) return;
    processedEventsCount.current = events.length;

    for (const event of newEvents) {
      if (event.event_type === "ballot_found") {
        setShowChips(true);
      }

      if (event.event_type === "report_complete") {
        setShowChips(false);
        setShowViewReport(true);
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: buildReportSummary(event.report),
          },
        ]);
      }

      if (event.event_type === "clarification_needed") {
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: event.question },
        ]);
      }

      if (event.event_type === "follow_up_response") {
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: event.answer },
        ]);
      }

      if (event.event_type === "error") {
        const errorMsg = event.recoverable
          ? `${event.message}\n\n${t("errors.retry")}`
          : event.message;
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: errorMsg },
        ]);
      }
    }
  }, [events]);

  function handleSend(content: string) {
    setMessages((prev) => [...prev, { role: "user", content }]);
    setShowChips(false);
    processedEventsCount.current = 0;
    sendMessage(content);
  }

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center bg-[var(--background)]">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-gray-300 border-t-[var(--accent)]" />
      </div>
    );
  }

  return (
    <div className="flex h-screen flex-col bg-[var(--background)]">
      <Header
        selectedElectionId={selectedElectionId}
        onElectionChange={(id) => {
          switchElection(id);
          // Reset chat state on election switch
          setMessages([]);
          setShowChips(false);
          setShowViewReport(false);
          welcomeSent.current = false;
          processedEventsCount.current = 0;
        }}
        disabled={isStreaming}
      />
      <MessageThread
        messages={messages}
        latestEvent={latestEvent}
        isStreaming={isStreaming}
        showViewReportButton={showViewReport}
        sessionId={sessionId ?? ""}
      />
      <PriorityChips onSubmit={handleSend} visible={showChips} />
      <InputBar onSend={handleSend} disabled={isStreaming} />
    </div>
  );
}
