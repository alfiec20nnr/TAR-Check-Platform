import { Chip, CircularProgress } from "@mui/material";

import type { SearchStatus } from "../api/types";

export default function StatusChip({ status }: { status: SearchStatus }) {
  switch (status) {
    case "pending":
      return <Chip size="small" label="Queued" variant="outlined" />;
    case "running":
      return (
        <Chip
          size="small"
          color="info"
          label="Running"
          icon={<CircularProgress size={12} color="inherit" />}
        />
      );
    case "completed":
      return <Chip size="small" color="success" label="Completed" variant="outlined" />;
    case "failed":
      return <Chip size="small" color="error" label="Failed" />;
  }
}
