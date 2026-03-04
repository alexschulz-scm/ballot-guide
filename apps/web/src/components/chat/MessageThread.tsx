"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";

import { t } from "@/lib/i18n";
import type { OrchestratorEvent } from "@/lib/types";

import MessageBubble from "./MessageBubble";
import ProgressBubble from "./ProgressBubble";

interface Props {
  messages: Array<{ role: "user" | "assistant"; content: string }>;
  latestEvent: OrchestratorEvent | null;
  isStreaming: boolean;
  showViewReportButton: boolean;
  sessionId: string;
}

export default function MessageThread({
  messages,
  latestEvent,
  isStreaming,
  showViewReportButton,
  sessionId,
}: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, latestEvent]);

  return (
    <div className="flex-1 overflow-y-auto px-4 py-4">
      {messages.map((msg, i) => (
        <MessageBubble key={i} role={msg.role} content={msg.content} />
      ))}
      <ProgressBubble latestEvent={latestEvent} isStreaming={isStreaming} />
      {showViewReportButton && (
        <div className="flex justify-start mb-3">
          <Link
            href={`/report/${sessionId}`}
            className="inline-block rounded-full bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white hover:opacity-90"
          >
            {t("chat.view_report_button")}
          </Link>
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  );
}
