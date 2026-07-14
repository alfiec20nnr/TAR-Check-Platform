import ShieldIcon from "@mui/icons-material/Shield";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { ApiError } from "../api/client";
import { useAuthStatus, useHealth, useLogin, useSetup } from "../api/hooks";
import { useSessionPresence } from "../components/Layout";

/** Login lock screen; on first launch it becomes the credential-setup form. */
export default function LoginPage() {
  const navigate = useNavigate();
  const { data: health } = useHealth();
  const { data: status, isLoading } = useAuthStatus();
  const login = useLogin();
  const setup = useSetup();
  useSessionPresence();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);

  const appName = health?.app_name ?? "Adverse Intelligence";
  const firstRun = status !== undefined && !status.configured;

  if (status?.authenticated) {
    return <Navigate to="/" replace />;
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (firstRun) {
      if (password.length < 8) {
        setError("Password must be at least 8 characters.");
        return;
      }
      if (password !== confirm) {
        setError("Passwords do not match.");
        return;
      }
    }
    try {
      if (firstRun) {
        await setup.mutateAsync({ username: username || "admin", password });
      } else {
        await login.mutateAsync({ username, password });
      }
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the server.");
    }
  };

  const busy = login.isPending || setup.isPending;

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
      <Card sx={{ width: "100%", maxWidth: 420 }} elevation={3}>
        <CardContent sx={{ p: 4 }}>
          <Stack spacing={1} alignItems="center" sx={{ mb: 3 }}>
            <ShieldIcon color="primary" sx={{ fontSize: 40 }} />
            <Typography variant="h5" component="h1" align="center">
              {appName}
            </Typography>
            <Typography variant="body2" color="text.secondary" align="center">
              {firstRun
                ? "Welcome — choose a username and password to protect this application."
                : "Sign in to continue."}
            </Typography>
          </Stack>
          <form onSubmit={submit}>
            <Stack spacing={2}>
              {error && <Alert severity="error">{error}</Alert>}
              <TextField
                label="Username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder={firstRun ? "admin" : undefined}
                autoComplete="username"
                autoFocus
                required={!firstRun}
                disabled={isLoading || busy}
              />
              <TextField
                label="Password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete={firstRun ? "new-password" : "current-password"}
                required
                disabled={isLoading || busy}
                helperText={firstRun ? "At least 8 characters." : undefined}
              />
              {firstRun && (
                <TextField
                  label="Confirm password"
                  type="password"
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  autoComplete="new-password"
                  required
                  disabled={busy}
                />
              )}
              <Button type="submit" variant="contained" size="large" disabled={isLoading || busy}>
                {firstRun ? "Create password & sign in" : "Sign in"}
              </Button>
            </Stack>
          </form>
        </CardContent>
      </Card>
    </Box>
  );
}
