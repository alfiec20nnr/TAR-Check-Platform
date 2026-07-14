import DarkModeIcon from "@mui/icons-material/DarkMode";
import HistoryIcon from "@mui/icons-material/History";
import LightModeIcon from "@mui/icons-material/LightMode";
import LogoutIcon from "@mui/icons-material/Logout";
import PersonSearchIcon from "@mui/icons-material/PersonSearch";
import ShieldIcon from "@mui/icons-material/Shield";
import SpaceDashboardIcon from "@mui/icons-material/SpaceDashboard";
import {
  Alert,
  AppBar,
  Box,
  Button,
  Container,
  IconButton,
  Toolbar,
  Tooltip,
  Typography,
} from "@mui/material";
import { useEffect, useState } from "react";
import { Link as RouterLink, Outlet, useLocation } from "react-router-dom";

import { useHealth, useLogout } from "../api/hooks";
import { useColorMode } from "../theme";
import WelcomeDialog from "./WelcomeDialog";

/** Lets the single-process (no-Docker) server stop itself when the last tab
 *  closes: announce open/close, and heartbeat while the tab is alive. All
 *  no-ops server-side when auto-shutdown mode is off (e.g. Docker). Also used
 *  by the login page so the server doesn't stop while someone signs in. */
export function useSessionPresence() {
  useEffect(() => {
    const open = () => {
      void fetch("/api/v1/session/open", { method: "POST" }).catch(() => {});
    };
    const onPageShow = (e: PageTransitionEvent) => {
      // Initial load is counted by the mount below; only re-announce when the
      // page is restored from the back/forward cache.
      if (e.persisted) open();
    };
    const onPageHide = () => {
      navigator.sendBeacon("/api/v1/session/close");
    };
    open();
    window.addEventListener("pageshow", onPageShow);
    window.addEventListener("pagehide", onPageHide);
    const heartbeat = setInterval(() => {
      void fetch("/health").catch(() => {});
    }, 15_000);
    return () => {
      window.removeEventListener("pageshow", onPageShow);
      window.removeEventListener("pagehide", onPageHide);
      clearInterval(heartbeat);
      // SPA unmount (e.g. login page → app): balance this component's open().
      // On a real tab close, pagehide has already fired and this never runs.
      navigator.sendBeacon("/api/v1/session/close");
    };
  }, []);
}

const NAV = [
  { to: "/", label: "Dashboard", icon: <SpaceDashboardIcon fontSize="small" /> },
  { to: "/search", label: "New Search", icon: <PersonSearchIcon fontSize="small" /> },
  { to: "/history", label: "History", icon: <HistoryIcon fontSize="small" /> },
];

export default function Layout() {
  const { mode, toggle } = useColorMode();
  const location = useLocation();
  const { data: health } = useHealth();
  const logout = useLogout();
  const [logoOk, setLogoOk] = useState(true);
  useSessionPresence();

  // Configurable display name (APP_NAME in .env, surfaced via /health).
  const appName = health?.app_name ?? "Adverse Intelligence";

  // Keep the browser tab title in sync with the configured name.
  useEffect(() => {
    document.title = appName;
  }, [appName]);

  return (
    <Box sx={{ minHeight: "100vh", display: "flex", flexDirection: "column" }}>
      <WelcomeDialog />
      <AppBar position="sticky" elevation={1} color="default">
        <Toolbar sx={{ gap: 2 }}>
          {logoOk ? (
            <Box
              component="img"
              src="/logo.png"
              alt={`${appName} logo`}
              onError={() => setLogoOk(false)}
              sx={{ height: 32, width: "auto", maxWidth: 160, borderRadius: 1, display: "block" }}
            />
          ) : (
            <ShieldIcon color="primary" />
          )}
          <Typography variant="h6" component={RouterLink} to="/" sx={{
            color: "inherit", textDecoration: "none", flexGrow: { xs: 1, sm: 0 }, mr: 2,
          }}>
            {appName}
          </Typography>
          <Box sx={{ display: "flex", gap: 1, flexGrow: 1 }}>
            {NAV.map((item) => (
              <Button
                key={item.to}
                component={RouterLink}
                to={item.to}
                startIcon={item.icon}
                color={location.pathname === item.to ? "primary" : "inherit"}
                sx={{ display: { xs: "none", sm: "inline-flex" } }}
              >
                {item.label}
              </Button>
            ))}
          </Box>
          <Tooltip title={mode === "light" ? "Switch to dark mode" : "Switch to light mode"}>
            <IconButton onClick={toggle} color="inherit" aria-label="toggle colour mode">
              {mode === "light" ? <DarkModeIcon /> : <LightModeIcon />}
            </IconButton>
          </Tooltip>
          <Tooltip title="Sign out">
            <IconButton
              onClick={() => logout.mutate()}
              color="inherit"
              aria-label="sign out"
              disabled={logout.isPending}
            >
              <LogoutIcon />
            </IconButton>
          </Tooltip>
        </Toolbar>
      </AppBar>
      {health?.mock_connectors && (
        <Alert severity="warning" sx={{ borderRadius: 0 }}>
          <strong>Demo mode</strong> — connectors are returning simulated sample data, not real
          records. Nothing shown relates to any real person. Set{" "}
          <code>MOCK_CONNECTORS=false</code> and add API keys in <code>.env</code> to search real
          sources.
        </Alert>
      )}
      <Container maxWidth="lg" sx={{ py: 3, flexGrow: 1 }}>
        <Outlet />
      </Container>
      <Box component="footer" sx={{ py: 2, textAlign: "center", opacity: 0.6 }}>
        <Typography variant="caption">
          {appName} (MVP) — for legitimate business due diligence only.
        </Typography>
      </Box>
    </Box>
  );
}
