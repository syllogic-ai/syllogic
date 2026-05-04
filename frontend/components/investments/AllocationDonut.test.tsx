import { render } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { AllocationDonut } from "./AllocationDonut";

describe("AllocationDonut", () => {
  it("renders one circle per segment + a track", () => {
    const { container } = render(
      <AllocationDonut
        segments={[
          { label: "ETF", pct: 60, color: "#000" },
          { label: "Cash", pct: 40, color: "#888" },
        ]}
      />
    );
    expect(container.querySelectorAll("circle").length).toBe(3); // track + 2 segments
  });
});
