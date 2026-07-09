import DescriptionIcon from "@mui/icons-material/Description";
import DownloadIcon from "@mui/icons-material/Download";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Grid2 as Grid,
  LinearProgress,
  Skeleton,
  Stack,
  Typography,
} from "@mui/material";
import { useState } from "react";
import { useParams } from "react-router-dom";

import { reportUrl } from "../api/client";
import { useSearchDetail } from "../api/hooks";
import ResultsTable from "../components/ResultsTable";
import RiskChip from "../components/RiskChip";
import StatusChip from "../components/StatusChip";

export default function SearchDetailPage() {
  const { searchId } = useParams<{ searchId: string }>();
  const { data, isPending, isError, error } = useSearchDetail(searchId);
  const [pdfNote, setPdfNote] = useState<string | null>(null);

  if (isPending) return <Skeleton variant="rounded" height={300} />;
  if (isError) return <Alert severity="error">{error.message}</Alert>;
  if (!data) return null;

  const inProgress = data.status === "pending" || data.status === "running";

  // PDF is generated server-side and is unavailable in some environments
  // (e.g. the no-Docker Windows setup) — fetch it so a failure can be shown
  // as a friendly note instead of a raw JSON error page.
  const downloadPdf = async () => {
    try {
      const resp = await fetch(reportUrl(data.id, "pdf"));
      if (!resp.ok) {
        let detail =
          "PDF export is unavailable here — download the report as HTML or JSON instead.";
        try {
          const body = await resp.json();
          if (typeof body.detail === "string") detail = body.detail;
        } catch {
          /* non-JSON error body */
        }
        setPdfNote(detail);
        return;
      }
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${data.report_reference ?? "report"}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch {
      setPdfNote("PDF download failed — try the HTML or JSON format instead.");
    }
  };

  return (
    <Grid container spacing={3}>
      <Grid size={12}>
        <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap" useFlexGap>
          <Typography variant="h5">{data.full_name}</Typography>
          <StatusChip status={data.status} />
          <RiskChip level={data.risk_level} score={data.risk_score_value} />
        </Stack>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
          Submitted {new Date(data.created_at).toLocaleString()}
          {data.date_of_birth ? ` · DOB ${data.date_of_birth}` : ""}
          {data.country ? ` · ${data.country}` : ""}
          {data.report_reference ? ` · Report ${data.report_reference}` : ""}
        </Typography>
      </Grid>

      {inProgress && (
        <Grid size={12}>
          <Card variant="outlined">
            <CardContent>
              <Typography gutterBottom>
                Search in progress — querying data sources, matching identities and
                generating the report…
              </Typography>
              <LinearProgress />
            </CardContent>
          </Card>
        </Grid>
      )}

      {data.status === "failed" && (
        <Grid size={12}>
          <Alert severity="error">Search failed: {data.error ?? "unknown error"}</Alert>
        </Grid>
      )}

      {data.status === "completed" && (
        <>
          <Grid size={12}>
            <Card variant="outlined">
              <CardContent>
                <Stack
                  direction={{ xs: "column", sm: "row" }}
                  spacing={2}
                  alignItems={{ sm: "center" }}
                  justifyContent="space-between"
                >
                  <Box>
                    <Typography variant="h6">Report {data.report_reference}</Typography>
                    <Typography variant="body2" color="text.secondary">
                      {data.results_count} result(s) from{" "}
                      {(data.sources_searched ?? []).length} source(s) in{" "}
                      {((data.duration_ms ?? 0) / 1000).toFixed(1)}s
                    </Typography>
                  </Box>
                  <Stack direction="row" spacing={1}>
                    <Button
                      variant="contained"
                      startIcon={<DownloadIcon />}
                      onClick={() => void downloadPdf()}
                    >
                      PDF
                    </Button>
                    <Button
                      variant="outlined"
                      startIcon={<DescriptionIcon />}
                      href={reportUrl(data.id, "html")}
                      target="_blank"
                    >
                      HTML
                    </Button>
                    <Button variant="outlined" href={reportUrl(data.id, "json")} target="_blank">
                      JSON
                    </Button>
                  </Stack>
                </Stack>
                {pdfNote && (
                  <Alert severity="info" onClose={() => setPdfNote(null)} sx={{ mt: 2 }}>
                    {pdfNote}
                  </Alert>
                )}
              </CardContent>
            </Card>
          </Grid>
          <Grid size={12}>
            <Typography variant="h6" gutterBottom>
              Results
            </Typography>
            <ResultsTable results={data.results} />
          </Grid>
        </>
      )}
    </Grid>
  );
}
