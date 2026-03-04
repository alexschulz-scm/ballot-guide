/**
 * @jest-environment jsdom
 */
import { render, screen } from "@testing-library/react";

import MessageThread from "../../../components/chat/MessageThread";

// Mock next/link to render plain <a> tags
jest.mock("next/link", () => {
  return ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  );
});

// Mock scrollIntoView
const mockScrollIntoView = jest.fn();
Element.prototype.scrollIntoView = mockScrollIntoView;

beforeEach(() => {
  jest.clearAllMocks();
});

describe("MessageThread", () => {
  it("scrolls to bottom on new message", () => {
    const { rerender } = render(
      <MessageThread
        messages={[{ role: "assistant", content: "Hello" }]}
        latestEvent={null}
        isStreaming={false}
        showViewReportButton={false}
        sessionId="s-1"
      />,
    );

    rerender(
      <MessageThread
        messages={[
          { role: "assistant", content: "Hello" },
          { role: "user", content: "Hi back" },
        ]}
        latestEvent={null}
        isStreaming={false}
        showViewReportButton={false}
        sessionId="s-1"
      />,
    );

    expect(mockScrollIntoView).toHaveBeenCalledWith({ behavior: "smooth" });
  });

  it("shows progress bubble while streaming", () => {
    render(
      <MessageThread
        messages={[{ role: "user", content: "33101" }]}
        latestEvent={{
          event_type: "item_analyzed",
          session_id: "s-1",
          timestamp: "2026-01-15T00:00:00Z",
          item_id: "m-1",
          item_title: "Amendment 1",
          items_complete: 1,
          items_total: 4,
        }}
        isStreaming={true}
        showViewReportButton={false}
        sessionId="s-1"
      />,
    );

    expect(screen.getByText(/Analyzing Amendment 1/)).toBeInTheDocument();
  });

  it("hides progress bubble after streaming ends", () => {
    render(
      <MessageThread
        messages={[{ role: "assistant", content: "Done!" }]}
        latestEvent={null}
        isStreaming={false}
        showViewReportButton={false}
        sessionId="s-1"
      />,
    );

    expect(screen.queryByText(/Getting started/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Analyzing/)).not.toBeInTheDocument();
  });
});
