import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import {
  Box,
  Chip,
  IconButton,
  Link,
  MenuItem,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TablePagination,
  TableRow,
  TableSortLabel,
  TextField,
  Typography,
} from "@mui/material";
import { useMemo, useState } from "react";

import type { SearchResultOut } from "../api/types";

type SortKey = "confidence" | "risk_contribution" | "event_date";

const CATEGORY_LABELS: Record<string, string> = {
  sanctions: "Sanctions",
  disqualification: "Disqualification",
  insolvency: "Insolvency",
  regulatory: "Regulatory",
  adverse_media: "Adverse media",
  directorship: "Directorship",
  web: "Web",
};

export default function ResultsTable({ results }: { results: SearchResultOut[] }) {
  const [filterText, setFilterText] = useState("");
  const [category, setCategory] = useState("all");
  const [sortKey, setSortKey] = useState<SortKey>("risk_contribution");
  const [sortAsc, setSortAsc] = useState(false);
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(10);

  const categories = useMemo(
    () => Array.from(new Set(results.map((r) => r.category))).sort(),
    [results],
  );

  const filtered = useMemo(() => {
    const text = filterText.toLowerCase();
    const rows = results.filter(
      (r) =>
        (category === "all" || r.category === category) &&
        (!text ||
          r.title.toLowerCase().includes(text) ||
          (r.description ?? "").toLowerCase().includes(text) ||
          r.source_name.toLowerCase().includes(text)),
    );
    rows.sort((a, b) => {
      const av = a[sortKey] ?? "";
      const bv = b[sortKey] ?? "";
      const cmp = av < bv ? -1 : av > bv ? 1 : 0;
      return sortAsc ? cmp : -cmp;
    });
    return rows;
  }, [results, filterText, category, sortKey, sortAsc]);

  const paged = filtered.slice(page * rowsPerPage, (page + 1) * rowsPerPage);

  const headerSort = (key: SortKey, label: string) => (
    <TableSortLabel
      active={sortKey === key}
      direction={sortKey === key && sortAsc ? "asc" : "desc"}
      onClick={() => {
        if (sortKey === key) setSortAsc(!sortAsc);
        else {
          setSortKey(key);
          setSortAsc(false);
        }
      }}
    >
      {label}
    </TableSortLabel>
  );

  return (
    <Paper variant="outlined">
      <Box sx={{ display: "flex", gap: 2, p: 2, flexWrap: "wrap" }}>
        <TextField
          size="small"
          label="Filter results"
          value={filterText}
          onChange={(e) => {
            setFilterText(e.target.value);
            setPage(0);
          }}
          sx={{ minWidth: 220 }}
        />
        <TextField
          size="small"
          select
          label="Category"
          value={category}
          onChange={(e) => {
            setCategory(e.target.value);
            setPage(0);
          }}
          sx={{ minWidth: 180 }}
        >
          <MenuItem value="all">All categories</MenuItem>
          {categories.map((c) => (
            <MenuItem key={c} value={c}>
              {CATEGORY_LABELS[c] ?? c}
            </MenuItem>
          ))}
        </TextField>
      </Box>
      <TableContainer>
        <Table size="small" aria-label="search results">
          <TableHead>
            <TableRow>
              <TableCell>Record</TableCell>
              <TableCell>Source</TableCell>
              <TableCell>Category</TableCell>
              <TableCell>{headerSort("event_date", "Date")}</TableCell>
              <TableCell align="right">{headerSort("confidence", "Confidence")}</TableCell>
              <TableCell align="right">{headerSort("risk_contribution", "Risk")}</TableCell>
              <TableCell align="center">Link</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {paged.map((r) => (
              <TableRow key={r.id} hover>
                <TableCell sx={{ maxWidth: 380 }}>
                  <Typography variant="body2" fontWeight={600}>
                    {r.title}
                  </Typography>
                  {r.description && (
                    <Typography variant="caption" color="text.secondary">
                      {r.description}
                    </Typography>
                  )}
                </TableCell>
                <TableCell>{r.source_name}</TableCell>
                <TableCell>
                  <Chip size="small" label={CATEGORY_LABELS[r.category] ?? r.category} />
                </TableCell>
                <TableCell>{r.event_date ?? "—"}</TableCell>
                <TableCell align="right">{r.confidence}%</TableCell>
                <TableCell align="right">{r.risk_contribution}</TableCell>
                <TableCell align="center">
                  {r.url ? (
                    <IconButton
                      size="small"
                      component={Link}
                      href={r.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      aria-label="open source"
                    >
                      <OpenInNewIcon fontSize="inherit" />
                    </IconButton>
                  ) : (
                    "—"
                  )}
                </TableCell>
              </TableRow>
            ))}
            {paged.length === 0 && (
              <TableRow>
                <TableCell colSpan={7} align="center">
                  <Typography color="text.secondary" sx={{ py: 2 }}>
                    No results match the current filters.
                  </Typography>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
      <TablePagination
        component="div"
        count={filtered.length}
        page={page}
        onPageChange={(_, p) => setPage(p)}
        rowsPerPage={rowsPerPage}
        onRowsPerPageChange={(e) => {
          setRowsPerPage(parseInt(e.target.value, 10));
          setPage(0);
        }}
        rowsPerPageOptions={[10, 25, 50]}
      />
    </Paper>
  );
}
