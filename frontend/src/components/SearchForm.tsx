import {
  Alert,
  Box,
  Button,
  Checkbox,
  FormControlLabel,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { useSubmitSearch } from "../api/hooks";

export default function SearchForm({ compact = false }: { compact?: boolean }) {
  const [fullName, setFullName] = useState("");
  const [dob, setDob] = useState("");
  const [country, setCountry] = useState("");
  const [licenceNumber, setLicenceNumber] = useState("");
  const [licenceConsent, setLicenceConsent] = useState(false);
  const submit = useSubmitSearch();
  const navigate = useNavigate();

  const licenceEntered = licenceNumber.trim().length > 0;

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    submit.mutate(
      {
        full_name: fullName.trim(),
        date_of_birth: dob || null,
        country: country.trim() || null,
        driving_licence_number: licenceNumber.trim() || null,
        licence_check_consent: licenceEntered ? licenceConsent : false,
      },
      { onSuccess: (search) => navigate(`/searches/${search.id}`) },
    );
  };

  return (
    <Box component="form" onSubmit={onSubmit} noValidate>
      <Stack spacing={2} direction={compact ? { xs: "column", md: "row" } : "column"}>
        <TextField
          label="Full name"
          value={fullName}
          onChange={(e) => setFullName(e.target.value)}
          required
          fullWidth
          autoFocus={!compact}
          inputProps={{ minLength: 2, maxLength: 200 }}
        />
        <TextField
          label="Date of birth (optional)"
          type="date"
          value={dob}
          onChange={(e) => setDob(e.target.value)}
          fullWidth
          InputLabelProps={{ shrink: true }}
        />
        <TextField
          label="Country (optional)"
          value={country}
          onChange={(e) => setCountry(e.target.value)}
          fullWidth
          placeholder="United Kingdom"
        />
        {!compact && (
          <>
            <TextField
              label="Driving licence number (optional)"
              value={licenceNumber}
              onChange={(e) => setLicenceNumber(e.target.value)}
              fullWidth
              placeholder="e.g. MORGA657054SM9IJ"
              inputProps={{ maxLength: 24 }}
              helperText="Enables the DVLA licence check (validity, endorsements, disqualifications)."
            />
            {licenceEntered && (
              <FormControlLabel
                control={
                  <Checkbox
                    checked={licenceConsent}
                    onChange={(e) => setLicenceConsent(e.target.checked)}
                    required
                  />
                }
                label={
                  <Typography variant="body2">
                    I confirm the driver has consented to a DVLA driving licence
                    data check. This attestation is recorded in the audit log.
                  </Typography>
                }
              />
            )}
          </>
        )}
        <Button
          type="submit"
          variant="contained"
          size="large"
          disabled={
            fullName.trim().length < 2 ||
            (licenceEntered && !licenceConsent) ||
            submit.isPending
          }
          sx={{ whiteSpace: "nowrap", px: 4 }}
        >
          {submit.isPending ? "Submitting…" : "Run search"}
        </Button>
      </Stack>
      {submit.isError && (
        <Alert severity="error" sx={{ mt: 2 }}>
          {submit.error.message}
        </Alert>
      )}
    </Box>
  );
}
