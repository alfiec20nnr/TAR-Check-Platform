import {
  Alert,
  Card,
  CardContent,
  Grid2 as Grid,
  Skeleton,
  Typography,
} from "@mui/material";

import { useDashboardStats } from "../api/hooks";
import SearchesTable from "../components/SearchesTable";
import SearchForm from "../components/SearchForm";

function StatCard({ label, value, accent }: { label: string; value: number; accent?: string }) {
  return (
    <Card variant="outlined" sx={{ height: "100%" }}>
      <CardContent>
        <Typography variant="overline" color="text.secondary">
          {label}
        </Typography>
        <Typography variant="h4" fontWeight={700} color={accent}>
          {value}
        </Typography>
      </CardContent>
    </Card>
  );
}

export default function DashboardPage() {
  const { data, isPending, isError, error } = useDashboardStats();

  return (
    <Grid container spacing={3}>
      <Grid size={12}>
        <Typography variant="h5" gutterBottom>
          Dashboard
        </Typography>
        <Card variant="outlined">
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Quick search
            </Typography>
            <SearchForm compact />
          </CardContent>
        </Card>
      </Grid>

      {isError && (
        <Grid size={12}>
          <Alert severity="error">Failed to load dashboard: {error.message}</Alert>
        </Grid>
      )}

      {isPending ? (
        <Grid size={12}>
          <Skeleton variant="rounded" height={120} />
        </Grid>
      ) : (
        data && (
          <>
            <Grid size={{ xs: 6, md: 3 }}>
              <StatCard label="Total searches" value={data.total_searches} />
            </Grid>
            <Grid size={{ xs: 6, md: 3 }}>
              <StatCard label="In progress" value={data.running_searches} accent="info.main" />
            </Grid>
            <Grid size={{ xs: 6, md: 3 }}>
              <StatCard label="Completed" value={data.completed_searches} accent="success.main" />
            </Grid>
            <Grid size={{ xs: 6, md: 3 }}>
              <StatCard label="High risk" value={data.high_risk_searches} accent="error.main" />
            </Grid>

            <Grid size={{ xs: 12, lg: 7 }}>
              <Typography variant="h6" gutterBottom>
                Recent searches
              </Typography>
              <SearchesTable searches={data.recent_searches} />
            </Grid>
            <Grid size={{ xs: 12, lg: 5 }}>
              <Typography variant="h6" gutterBottom>
                High-risk searches
              </Typography>
              <SearchesTable
                searches={data.high_risk_recent}
                emptyMessage="No high-risk searches."
              />
            </Grid>
          </>
        )
      )}
    </Grid>
  );
}
