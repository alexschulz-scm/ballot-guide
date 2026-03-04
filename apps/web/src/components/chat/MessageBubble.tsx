import type { ReactNode } from "react";

interface Props {
  role: "user" | "assistant";
  content: string;
}

export default function MessageBubble({ role, content }: Props) {
  const isUser = role === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} mb-3`}>
      <div
        className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
          isUser
            ? "rounded-br-sm bg-[var(--accent)] text-white"
            : "rounded-bl-sm bg-gray-100 text-gray-800"
        }`}
      >
        {isUser ? <PlainText text={content} /> : <RichText text={content} />}
      </div>
    </div>
  );
}

function PlainText({ text }: { text: string }) {
  return (
    <>
      {text.split("\n").map((line, i) => (
        <span key={i}>
          {i > 0 && <br />}
          {line}
        </span>
      ))}
    </>
  );
}

function RichText({ text }: { text: string }) {
  const blocks = text.split("\n");
  const elements: ReactNode[] = [];
  let listItems: ReactNode[] = [];
  let key = 0;

  function flushList() {
    if (listItems.length > 0) {
      elements.push(
        <ul key={key++} className="my-1 ml-4 list-disc space-y-0.5">
          {listItems}
        </ul>
      );
      listItems = [];
    }
  }

  for (const line of blocks) {
    const trimmed = line.trim();

    if (trimmed === "") {
      flushList();
      elements.push(<div key={key++} className="h-2" />);
      continue;
    }

    if (trimmed === "---") {
      flushList();
      elements.push(<hr key={key++} className="my-2 border-gray-300" />);
      continue;
    }

    const h3Match = trimmed.match(/^###\s+(.+)/);
    if (h3Match) {
      flushList();
      elements.push(
        <h3 key={key++} className="mt-3 mb-1 font-semibold">
          {renderInline(h3Match[1])}
        </h3>
      );
      continue;
    }

    const h2Match = trimmed.match(/^##\s+(.+)/);
    if (h2Match) {
      flushList();
      elements.push(
        <h2 key={key++} className="mt-3 mb-1 text-base font-semibold">
          {renderInline(h2Match[1])}
        </h2>
      );
      continue;
    }

    if (trimmed.match(/^[-*]\s+/)) {
      const itemText = trimmed.replace(/^[-*]\s+/, "");
      listItems.push(<li key={key++}>{renderInline(itemText)}</li>);
      continue;
    }

    flushList();
    elements.push(
      <p key={key++} className="my-0.5">
        {renderInline(trimmed)}
      </p>
    );
  }

  flushList();
  return <>{elements}</>;
}

function renderInline(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  // Regex: **bold**, *italic*, [text](url)
  const re = /(\*\*(.+?)\*\*)|(\*(.+?)\*)|(\[([^\]]+)\]\(([^)]+)\))/g;
  let lastIndex = 0;
  let key = 0;
  let match: RegExpExecArray | null;

  while ((match = re.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index));
    }

    if (match[1]) {
      // **bold**
      nodes.push(
        <strong key={key++} className="font-semibold">
          {match[2]}
        </strong>
      );
    } else if (match[3]) {
      // *italic*
      nodes.push(<em key={key++}>{match[4]}</em>);
    } else if (match[5]) {
      // [text](url)
      nodes.push(
        <a
          key={key++}
          href={match[7]}
          target="_blank"
          rel="noopener noreferrer"
          className="underline"
        >
          {match[6]}
        </a>
      );
    }

    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex));
  }

  return nodes;
}
