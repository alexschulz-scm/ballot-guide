"use client";

import { useState } from "react";

import { t } from "@/lib/i18n";

interface Props {
  onSend: (content: string) => void;
  disabled: boolean;
  placeholder?: string;
}

export default function InputBar({ onSend, disabled, placeholder }: Props) {
  const [value, setValue] = useState("");

  function handleSend() {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  return (
    <div className="flex items-center gap-2 border-t border-gray-200 bg-white px-4 py-3">
      <input
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        placeholder={placeholder ?? t("chat.input_placeholder")}
        className="flex-1 rounded-full border border-gray-300 px-4 py-2 text-sm outline-none focus:border-[var(--accent)] disabled:opacity-50"
        aria-label={t("chat.input_placeholder")}
      />
      <button
        type="button"
        onClick={handleSend}
        disabled={disabled || !value.trim()}
        className="rounded-full bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50 disabled:cursor-not-allowed"
        aria-label="Send"
      >
        Send
      </button>
    </div>
  );
}
