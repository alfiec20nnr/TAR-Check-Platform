import {
  Card,
  CardContent,
  Chip,
  Grid2 as Grid,
  Stack,
  Typography,
} from "@mui/material";

import { useSources } from "../api/hooks";
import SearchForm from "../components/SearchForm";

export default function NewSearchPage() {
  const { data: sources } = useSources();

  return (
    <Grid container spacing={3}>
      <Grid size={{ xs: 12, md: 7 }}>
        <Typography variant="h5" gutterBottom>
          New search
        </Typography>
        <Card variant="outlined">
          <CardContent>
            <Typography color="text.secondary" paragraph>
              Search for an individual across public UK data sources. Only the full
              name is required — date of birth and country improve identity-match
              confidence.
            </Typography>
            <SearchForm />
          </CardContent>
        </Card>
      </Grid>
      <Grid size={{ xs: 12, md: 5 }}>
        <Typography variant="h5" gutterBottom>
          Sources searched
        </Typography>
        <Card variant="outlined">
          <CardContent>
            <Stack spacing={1.5}>
              {(sources ?? []).map((s) => (
                <Stack key={s.name} direction="row" spacing={1} alignItems="baseline">
                  <Chip
                    size="small"
                    label={!s.enabled ? "off" : s.configured ? "on" : "needs API key"}
                    color={!s.enabled ? "default" : s.configured ? "success" : "warning"}
                    variant="outlined"
                  />
                  <div>
                    <Typography variant="body2" fontWeight={600}>
                      {s.display_name}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {s.description}
                      {s.enabled && !s.configured &&
                        " — skipped until credentials are added to .env"}
                    </Typography>
                  </div>
                </Stack>
              ))}
            </Stack>
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );
}
