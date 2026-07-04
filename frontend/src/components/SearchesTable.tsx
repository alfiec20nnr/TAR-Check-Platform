import {
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import { useNavigate } from "react-router-dom";

import type { SearchOut } from "../api/types";
import RiskChip from "./RiskChip";
import StatusChip from "./StatusChip";

export default function SearchesTable({
  searches,
  emptyMessage = "No searches yet.",
}: {
  searches: SearchOut[];
  emptyMessage?: string;
}) {
  const navigate = useNavigate();

  if (searches.length === 0) {
    return (
      <Typography color="text.secondary" sx={{ py: 3, textAlign: "center" }}>
        {emptyMessage}
      </Typography>
    );
  }

  return (
    <TableContainer component={Paper} variant="outlined">
      <Table size="small" aria-label="searches">
        <TableHead>
          <TableRow>
            <TableCell>Subject</TableCell>
            <TableCell>Submitted</TableCell>
            <TableCell>Status</TableCell>
            <TableCell align="right">Results</TableCell>
            <TableCell>Risk</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {searches.map((s) => (
            <TableRow
              key={s.id}
              hover
              sx={{ cursor: "pointer" }}
              onClick={() => navigate(`/searches/${s.id}`)}
            >
              <TableCell>
                <Typography variant="body2" fontWeight={600}>
                  {s.full_name}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {s.country ?? "—"}
                </Typography>
              </TableCell>
              <TableCell>{new Date(s.created_at).toLocaleString()}</TableCell>
              <TableCell>
                <StatusChip status={s.status} />
              </TableCell>
              <TableCell align="right">{s.results_count}</TableCell>
              <TableCell>
                <RiskChip level={s.risk_level} score={s.risk_score_value} />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}
