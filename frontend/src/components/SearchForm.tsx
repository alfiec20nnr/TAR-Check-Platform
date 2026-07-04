import { Alert, Box, Button, Stack, TextField } from "@mui/material";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { useSubmitSearch } from "../api/hooks";

export default function SearchForm({ compact = false }: { compact?: boolean }) {
  const [fullName, setFullName] = useState("");
  const [dob, setDob] = useState("");
  const [country, setCountry] = useState("");
  const submit = useSubmitSearch();
  const navigate = useNavigate();

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    submit.mutate(
      {
        full_name: fullName.trim(),
        date_of_birth: dob || null,
        country: country.trim() || null,
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
        <Button
          type="submit"
          variant="contained"
          size="large"
          disabled={fullName.trim().length < 2 || submit.isPending}
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
