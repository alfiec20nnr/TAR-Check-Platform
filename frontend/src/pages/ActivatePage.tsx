import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import KeyIcon from "@mui/icons-material/Key";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  IconButton,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { ApiError } from "../api/client";
import { useActivate, useHealth, useLicenceStatus } from "../api/hooks";
import { useSessionPresence } from "../components/Layout";

/** Shown on a machine without a valid activation code: displays this
 *  machine's code so the user can request activation from their provider. */
export default function ActivatePage() {
  const navigate = useNavigate();
  const { data: health } = useHealth();
  const { data: status } = useLicenceStatus();
  const activate = useActivate();
  useSessionPresence();

  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const appName = health?.app_name ?? "Adverse Intelligence";

  if (status?.activated) {
    return <Navigate to="/login" replace />;
  }

  const copyMachineCode = async () => {
    if (!status) return;
    try {
      await navigator.clipboard.writeText(status.machine_code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard unavailable — the code is visible to copy by hand */
    }
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await activate.mutateAsync({ code });
      navigate("/login", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the server.");
    }
  };

  return (
    <Box
      sx={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        p: 2,
      }}
    >
      <Card sx={{ width: "100%", maxWidth: 480 }} elevation={3}>
        <CardContent sx={{ p: 4 }}>
          <Stack spacing={1} alignItems="center" sx={{ mb: 3 }}>
            <KeyIcon color="primary" sx={{ fontSize: 40 }} />
            <Typography variant="h5" component="h1" align="center">
              {appName}
            </Typography>
            <Typography variant="body2" color="text.secondary" align="center">
              This copy is not activated on this computer. Send the machine
              code below to your provider and enter the activation code you
              receive back.
            </Typography>
          </Stack>
          <Stack spacing={2}>
            <Box
              sx={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 1,
                p: 2,
                borderRadius: 1,
                bgcolor: "action.hover",
              }}
            >
              <Typography
                variant="h6"
                sx={{ fontFamily: "monospace", letterSpacing: 1 }}
                aria-label="machine code"
              >
                {status?.machine_code ?? "…"}
              </Typography>
              <Tooltip title={copied ? "Copied!" : "Copy machine code"}>
                <IconButton onClick={copyMachineCode} size="small" aria-label="copy machine code">
                  <ContentCopyIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            </Box>
            <form onSubmit={submit}>
              <Stack spacing={2}>
                {error && <Alert severity="error">{error}</Alert>}
                <TextField
                  label="Activation code"
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  multiline
                  minRows={2}
                  required
                  autoFocus
                  disabled={activate.isPending}
                  placeholder="Paste the activation code from your provider"
                />
                <Button
                  type="submit"
                  variant="contained"
                  size="large"
                  disabled={activate.isPending || !code.trim()}
                >
                  Activate
                </Button>
              </Stack>
            </form>
          </Stack>
        </CardContent>
      </Card>
    </Box>
  );
}
