import { t } from "../../lib/i18n";

describe("t() — i18n lookup", () => {
  it("returns the correct string for a simple key", () => {
    expect(t("report.for_label")).toBe("For");
  });

  it("interpolates a single variable", () => {
    expect(t("report.no_position", { topic: "Housing" })).toBe(
      "No public statement found on Housing.",
    );
  });

  it("navigates deeply nested keys", () => {
    expect(t("chat.welcome")).toBe(
      "Hi — I'm here to help you understand your Florida ballot.",
    );
  });

  it("returns the key itself when the path is missing", () => {
    expect(t("nonexistent.key.path")).toBe("nonexistent.key.path");
  });

  it("interpolates multiple variables in one string", () => {
    expect(
      t("shared_report.disclaimer", {
        priorities: "housing, education",
      }),
    ).toBe(
      "This guide was personalized for priorities: housing, education. Your ballot items may differ if you live in a different district.",
    );
  });
});
