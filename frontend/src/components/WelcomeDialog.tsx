import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  List,
  ListItem,
  ListItemText,
  Typography,
} from "@mui/material";
import { useState } from "react";

/** Shown once per browser session: the user must acknowledge what the
 *  platform is, how to use it, and how to read its output before searching. */
const STORAGE_KEY = "aip-welcome-acknowledged";

export default function WelcomeDialog() {
  const [open, setOpen] = useState(
    () => sessionStorage.getItem(STORAGE_KEY) !== "true",
  );

  const acknowledge = () => {
    sessionStorage.setItem(STORAGE_KEY, "true");
    setOpen(false);
  };

  return (
    <Dialog
      open={open}
      maxWidth="sm"
      fullWidth
      disableEscapeKeyDown
      aria-labelledby="welcome-dialog-title"
    >
      <DialogTitle id="welcome-dialog-title" sx={{ display: "flex", alignItems: "center", gap: 1 }}>
        <InfoOutlinedIcon color="primary" />
        Welcome to the Adverse Intelligence Platform
      </DialogTitle>
      <DialogContent dividers>
        <Typography variant="body2" paragraph>
          AIP searches publicly available sources for information about an individual, matches
          the results to your search subject, and produces a risk-scored report. It is intended
          for legitimate business due diligence, compliance, and vetting only.
        </Typography>
        <Typography variant="subtitle2" gutterBottom>
          How to use it
        </Typography>
        <Typography variant="body2" paragraph>
          Start a search from <strong>New Search</strong> with the person&apos;s full name — adding
          a date of birth and country greatly improves matching accuracy. The search runs in the
          background; when it completes you can review the findings and download the report from
          the search page or <strong>History</strong>.
        </Typography>
        <Typography variant="subtitle2" gutterBottom>
          Please be aware
        </Typography>
        <List dense disablePadding sx={{ listStyleType: "disc", pl: 3 }}>
          <ListItem sx={{ display: "list-item", pl: 0 }}>
            <ListItemText
              primaryTypographyProps={{ variant: "body2" }}
              primary="Results are not guaranteed to be complete or accurate — always verify findings against the original sources linked in the report."
            />
          </ListItem>
          <ListItem sx={{ display: "list-item", pl: 0 }}>
            <ListItemText
              primaryTypographyProps={{ variant: "body2" }}
              primary="Common names (e.g. John Smith) tend to produce higher risk scores simply because more sources mention that name — many results may relate to different people. Check the confidence score on each finding."
            />
          </ListItem>
          <ListItem sx={{ display: "list-item", pl: 0 }}>
            <ListItemText
              primaryTypographyProps={{ variant: "body2" }}
              primary="A source appearing in a report is not automatically negative — directorships, web mentions, and social media profiles are often neutral, informational records."
            />
          </ListItem>
        </List>
        <Box sx={{ mt: 2 }}>
          <Alert severity="info" variant="outlined">
            The AI summary distinguishes allegations from proven outcomes, but the final judgement
            on relevance and risk is always yours.
          </Alert>
        </Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={acknowledge} variant="contained" autoFocus>
          I understand
        </Button>
      </DialogActions>
    </Dialog>
  );
}
