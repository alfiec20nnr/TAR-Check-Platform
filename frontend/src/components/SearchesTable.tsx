import {
  Checkbox,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tooltip,
  Typography,
} from "@mui/material";
import { useNavigate } from "react-router-dom";

import type { SearchOut } from "../api/types";
import RiskChip from "./RiskChip";
import StatusChip from "./StatusChip";

const TERMINAL = new Set(["completed", "failed"]);

export default function SearchesTable({
  searches,
  emptyMessage = "No searches yet.",
  selected,
  onToggle,
  onToggleAll,
}: {
  searches: SearchOut[];
  emptyMessage?: string;
  /** When provided, rows become individually selectable for deletion. */
  selected?: Set<string>;
  onToggle?: (id: string) => void;
  onToggleAll?: (ids: string[]) => void;
}) {
  const navigate = useNavigate();
  const selectable = selected !== undefined && onToggle !== undefined;
  // Only finished searches can be deleted; running ones stay unselectable.
  const deletableIds = searches.filter((s) => TERMINAL.has(s.status)).map((s) => s.id);
  const allSelected =
    deletableIds.length > 0 && deletableIds.every((id) => selected?.has(id));

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
            {selectable && (
              <TableCell padding="checkbox">
                <Checkbox
                  size="small"
                  checked={allSelected}
                  indeterminate={!allSelected && (selected?.size ?? 0) > 0}
                  onChange={() => onToggleAll?.(deletableIds)}
                  inputProps={{ "aria-label": "select all searches on this page" }}
                />
              </TableCell>
            )}
            <TableCell>Subject</TableCell>
            <TableCell>Submitted</TableCell>
            <TableCell>Run by</TableCell>
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
              selected={selected?.has(s.id) ?? false}
            >
              {selectable && (
                <TableCell padding="checkbox" onClick={(e) => e.stopPropagation()}>
                  <Tooltip
                    title={
                      TERMINAL.has(s.status)
                        ? ""
                        : "Still running — cannot be deleted yet"
                    }
                  >
                    <span>
                      <Checkbox
                        size="small"
                        checked={selected?.has(s.id) ?? false}
                        disabled={!TERMINAL.has(s.status)}
                        onChange={() => onToggle?.(s.id)}
                        inputProps={{ "aria-label": `select search for ${s.full_name}` }}
                      />
                    </span>
                  </Tooltip>
                </TableCell>
              )}
              <TableCell>
                <Typography variant="body2" fontWeight={600}>
                  {s.full_name}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {s.country ?? "—"}
                </Typography>
              </TableCell>
              <TableCell>{new Date(s.created_at).toLocaleString()}</TableCell>
              <TableCell>{s.created_by ?? "—"}</TableCell>
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
