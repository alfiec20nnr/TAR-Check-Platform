import {
  Alert,
  Box,
  MenuItem,
  Skeleton,
  TablePagination,
  TextField,
  Typography,
} from "@mui/material";
import { useState } from "react";

import { useSearches } from "../api/hooks";
import SearchesTable from "../components/SearchesTable";

export default function HistoryPage() {
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(20);
  const [status, setStatus] = useState("");
  const [riskLevel, setRiskLevel] = useState("");

  const { data, isPending, isError, error } = useSearches(
    page + 1,
    pageSize,
    status || undefined,
    riskLevel || undefined,
  );

  return (
    <Box>
      <Typography variant="h5" gutterBottom>
        Search history
      </Typography>
      <Typography variant="body2" color="text.secondary" paragraph>
        Complete, append-only history of every search run on this platform.
      </Typography>

      <Box sx={{ display: "flex", gap: 2, mb: 2, flexWrap: "wrap" }}>
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
      </Box>

      {isError && <Alert severity="error">{error.message}</Alert>}
      {isPending ? (
        <Skeleton variant="rounded" height={300} />
      ) : (
        data && (
          <>
            <SearchesTable searches={data.items} />
            <TablePagination
              component="div"
              count={data.total}
              page={page}
              onPageChange={(_, p) => setPage(p)}
              rowsPerPage={pageSize}
              onRowsPerPageChange={(e) => {
                setPageSize(parseInt(e.target.value, 10));
                setPage(0);
              }}
              rowsPerPageOptions={[10, 20, 50]}
            />
          </>
        )
      )}
    </Box>
  );
}
