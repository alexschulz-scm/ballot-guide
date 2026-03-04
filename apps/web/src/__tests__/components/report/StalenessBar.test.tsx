/**
 * @jest-environment jsdom
 */
import { render, screen } from "@testing-library/react";

import StalenessBar from "../../../components/report/StalenessBar";

const noop = () => {};

describe("StalenessBar", () => {
  it("renders nothing for fresh", () => {
    const { container } = render(
      <StalenessBar freshness="fresh" onRefresh={noop} />,
    );
    expect(container.innerHTML).toBe("");
  });

  it("renders a blue banner for stale", () => {
    render(<StalenessBar freshness="stale" onRefresh={noop} />);
    const banner = screen.getByRole("alert");
    expect(banner).toHaveClass("bg-blue-50");
    expect(screen.getByText(/has been updated/)).toBeInTheDocument();
    expect(screen.getByText("Refresh")).toBeInTheDocument();
  });

  it("renders a yellow banner for very_stale", () => {
    render(<StalenessBar freshness="very_stale" onRefresh={noop} />);
    const banner = screen.getByRole("alert");
    expect(banner).toHaveClass("bg-yellow-50");
    expect(screen.getByText(/more than 7 days old/)).toBeInTheDocument();
    expect(screen.getByText("Get Updated Guide")).toBeInTheDocument();
  });
});
