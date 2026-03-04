/**
 * @jest-environment jsdom
 */
import { fireEvent, render, screen } from "@testing-library/react";

import PriorityChips from "../../../components/chat/PriorityChips";

describe("PriorityChips", () => {
  it("toggles chip selection on click", () => {
    const onSubmit = jest.fn();
    render(<PriorityChips onSubmit={onSubmit} visible={true} />);

    const housingChip = screen.getByText(/Housing & Rent/);
    fireEvent.click(housingChip);

    // Selected chip should have accent background class
    expect(housingChip).toHaveClass("bg-[var(--accent)]");

    // Click again to deselect
    fireEvent.click(housingChip);
    expect(housingChip).not.toHaveClass("bg-[var(--accent)]");
  });

  it("allows multiple chips to be selected", () => {
    const onSubmit = jest.fn();
    render(<PriorityChips onSubmit={onSubmit} visible={true} />);

    fireEvent.click(screen.getByText(/Housing & Rent/));
    fireEvent.click(screen.getByText(/Education & Schools/));

    expect(screen.getByText(/Housing & Rent/)).toHaveClass("bg-[var(--accent)]");
    expect(screen.getByText(/Education & Schools/)).toHaveClass("bg-[var(--accent)]");
  });

  it("formats message correctly on submit", () => {
    const onSubmit = jest.fn();
    render(<PriorityChips onSubmit={onSubmit} visible={true} />);

    fireEvent.click(screen.getByText(/Housing & Rent/));
    fireEvent.click(screen.getByText(/Education & Schools/));

    const submitButton = screen.getByText("See My Ballot Guide");
    fireEvent.click(submitButton);

    expect(onSubmit).toHaveBeenCalledWith(
      expect.stringContaining("I care about:"),
    );
    expect(onSubmit).toHaveBeenCalledWith(
      expect.stringContaining("Housing & Rent"),
    );
    expect(onSubmit).toHaveBeenCalledWith(
      expect.stringContaining("Education & Schools"),
    );
  });

  it("does not submit when no chips are selected", () => {
    const onSubmit = jest.fn();
    render(<PriorityChips onSubmit={onSubmit} visible={true} />);

    const submitButton = screen.getByText("See My Ballot Guide");
    fireEvent.click(submitButton);

    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("renders null when not visible", () => {
    const onSubmit = jest.fn();
    const { container } = render(
      <PriorityChips onSubmit={onSubmit} visible={false} />,
    );
    expect(container.innerHTML).toBe("");
  });
});
