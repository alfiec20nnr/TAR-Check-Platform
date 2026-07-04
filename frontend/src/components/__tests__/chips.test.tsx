import { render, screen } from "@testing-library/react";

import RiskChip from "../RiskChip";
import StatusChip from "../StatusChip";

describe("RiskChip", () => {
  it("renders a placeholder when no level is set", () => {
    render(<RiskChip level={null} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("renders level and score", () => {
    render(<RiskChip level="critical" score={92.5} />);
    expect(screen.getByText("CRITICAL · 92.5")).toBeInTheDocument();
  });

  it("renders level without score", () => {
    render(<RiskChip level="low" />);
    expect(screen.getByText("LOW")).toBeInTheDocument();
  });
});

describe("StatusChip", () => {
  it.each([
    ["pending", "Queued"],
    ["running", "Running"],
    ["completed", "Completed"],
    ["failed", "Failed"],
  ] as const)("renders %s as %s", (status, label) => {
    render(<StatusChip status={status} />);
    expect(screen.getByText(label)).toBeInTheDocument();
  });
});
