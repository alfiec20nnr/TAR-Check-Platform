import { Chip } from "@mui/material";

import type { RiskLevel } from "../api/types";

const COLORS: Record<RiskLevel, "success" | "warning" | "error"> = {
  low: "success",
  medium: "warning",
  high: "error",
  critical: "error",
};

export default function RiskChip({
  level,
  score,
}: {
  level: RiskLevel | null;
  score?: number | null;
}) {
  if (!level) return <Chip size="small" label="—" variant="outlined" />;
  const label = score != null ? `${level.toUpperCase()} · ${score}` : level.toUpperCase();
  return (
    <Chip
      size="small"
      color={COLORS[level]}
      variant={level === "critical" ? "filled" : "outlined"}
      label={label}
      sx={level === "critical" ? { fontWeight: 700 } : undefined}
    />
  );
}
