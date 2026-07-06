import DeleteIcon from "@mui/icons-material/Delete";
import DeleteSweepIcon from "@mui/icons-material/DeleteSweep";
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  MenuItem,
  Skeleton,
  TablePagination,
  TextField,
  Typography,
} from "@mui/material";
import { useState } from "react";

import { useClearHistory, useDeleteSearches, useSearches } from "../api/hooks";
import SearchesTable from "../components/SearchesTable";

type ConfirmAction = "selected" | "all" | null;

export default function HistoryPage() {
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(20);
  const [status, setStatus] = useState("");
  const [riskLevel, setRiskLevel] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [confirm, setConfirm] = useState<ConfirmAction>(null);

  const { data, isPending, isError, error } = useSearches(
    page + 1,
    pageSize,
    status || undefined,
    riskLevel || undefined,
  );
  const deleteSearches = useDeleteSearches();
  const clearHistory = useClearHistory();
  const busy = deleteSearches.isPending || clearHistory.isPending;

  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const toggleAll = (deletableIds: string[]) =>
    setSelected((prev) => {
      const allOn = deletableIds.length > 0 && deletableIds.every((id) => prev.has(id));
      return allOn ? new Set<string>() : new Set(deletableIds);
    });

  const runConfirmed = () => {
    const action = confirm;
    setConfirm(null);
    if (action === "selected") {
      deleteSearches.mutate([...selected], { onSuccess: () => setSelected(new Set()) });
    } else if (action === "all") {
      clearHistory.mutate(undefined, { onSuccess: () => setSelected(new Set()) });
    }
  };

  return (
    <Box>
      <Typography variant="h5" gutterBottom>
        Search history
      </Typography>
      <Typography variant="body2" color="text.secondary" paragraph>
        History entries can be deleted; the audit log permanently records that
        each search (and each deletion) happened.
      </Typography>

      <Box sx={{ display: "flex", gap: 2, mb: 2, flexWrap: "wrap", alignItems: "center" }}>
        <TextField
          size="small"
          select
          label="Status"
          value={status}
          onChange={(e) => {
            setStatus(e.target.value);
            setPage(0);
          }}
          sx={{ minWidth: 160 }}
        >
          <MenuItem value="">All</MenuItem>
          <MenuItem value="pending">Queued</MenuItem>
          <MenuItem value="running">Running</MenuItem>
          <MenuItem value="completed">Completed</MenuItem>
          <MenuItem value="failed">Failed</MenuItem>
        </TextField>
        <TextField
          size="small"
          select
          label="Risk level"
          value={riskLevel}
          onChange={(e) => {
            setRiskLevel(e.target.value);
            setPage(0);
          }}
          sx={{ minWidth: 160 }}
        >
          <MenuItem value="">All</MenuItem>
          <MenuItem value="low">Low</MenuItem>
          <MenuItem value="medium">Medium</MenuItem>
          <MenuItem value="high">High</MenuItem>
          <MenuItem value="critical">Critical</MenuItem>
        </TextField>
        <Box sx={{ flexGrow: 1 }} />
        <Button
          size="small"
          color="error"
          variant="outlined"
          startIcon={<DeleteIcon />}
          disabled={selected.size === 0 || busy}
          onClick={() => setConfirm("selected")}
        >
          Delete selected ({selected.size})
        </Button>
        <Button
          size="small"
          color="error"
          variant="contained"
          startIcon={<DeleteSweepIcon />}
          disabled={busy || (data?.total ?? 0) === 0}
          onClick={() => setConfirm("all")}
        >
          Clear history
        </Button>
      </Box>

      {isError && <Alert severity="error">{error.message}</Alert>}
      {deleteSearches.isError && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {deleteSearches.error.message}
        </Alert>
      )}
      {clearHistory.isError && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {clearHistory.error.message}
        </Alert>
      )}

      {isPending ? (
        <Skeleton variant="rounded" height={300} />
      ) : (
        data && (
          <>
            <SearchesTable
              searches={data.items}
              selected={selected}
              onToggle={toggle}
              onToggleAll={toggleAll}
            />
            <TablePagination
              component="div"
              count={data.total}
              page={page}
              onPageChange={(_, p) => {
                setPage(p);
                setSelected(new Set());
              }}
              rowsPerPage={pageSize}
              onRowsPerPageChange={(e) => {
                setPageSize(parseInt(e.target.value, 10));
                setPage(0);
                setSelected(new Set());
              }}
              rowsPerPageOptions={[10, 20, 50]}
            />
          </>
        )
      )}

      <Dialog open={confirm !== null} onClose={() => setConfirm(null)}>
        <DialogTitle>
          {confirm === "all" ? "Clear entire search history?" : "Delete selected searches?"}
        </DialogTitle>
        <DialogContent>
          <DialogContentText>
            {confirm === "all"
              ? "Every completed or failed search, including its results and stored reports, will be permanently deleted. Running searches are not affected."
              : `${selected.size} search(es), including their results and stored reports, will be permanently deleted.`}{" "}
            This cannot be undone. The audit log keeps a permanent record that the
            searches — and this deletion — took place.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirm(null)}>Cancel</Button>
          <Button color="error" variant="contained" onClick={runConfirmed}>
            {confirm === "all" ? "Clear history" : "Delete"}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
