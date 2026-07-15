import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  TextField,
} from "@mui/material";
import { useState } from "react";

import { useChangePassword } from "../api/hooks";

export default function ChangePasswordDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const changePassword = useChangePassword();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const reset = () => {
    setCurrent("");
    setNext("");
    setConfirm("");
    setError(null);
    setDone(false);
    changePassword.reset();
  };

  const close = () => {
    reset();
    onClose();
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (next.length < 8) {
      setError("New password must be at least 8 characters.");
      return;
    }
    if (next !== confirm) {
      setError("New passwords do not match.");
      return;
    }
    changePassword.mutate(
      { current_password: current, new_password: next },
      {
        onSuccess: () => setDone(true),
        onError: (err) => setError(err.message),
      },
    );
  };

  return (
    <Dialog open={open} onClose={close} maxWidth="xs" fullWidth>
      <form onSubmit={submit}>
        <DialogTitle>Change password</DialogTitle>
        <DialogContent>
          {done ? (
            <Alert severity="success">Password changed.</Alert>
          ) : (
            <Stack spacing={2} sx={{ mt: 1 }}>
              {error && <Alert severity="error">{error}</Alert>}
              <TextField
                label="Current password"
                type="password"
                autoComplete="current-password"
                value={current}
                onChange={(e) => setCurrent(e.target.value)}
                required
                autoFocus
                fullWidth
              />
              <TextField
                label="New password"
                type="password"
                autoComplete="new-password"
                value={next}
                onChange={(e) => setNext(e.target.value)}
                required
                helperText="At least 8 characters"
                fullWidth
              />
              <TextField
                label="Confirm new password"
                type="password"
                autoComplete="new-password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                required
                fullWidth
              />
            </Stack>
          )}
        </DialogContent>
        <DialogActions>
          {done ? (
            <Button onClick={close}>Close</Button>
          ) : (
            <>
              <Button onClick={close}>Cancel</Button>
              <Button type="submit" variant="contained" disabled={changePassword.isPending}>
                Change password
              </Button>
            </>
          )}
        </DialogActions>
      </form>
    </Dialog>
  );
}
