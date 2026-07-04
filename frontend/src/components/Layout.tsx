import DarkModeIcon from "@mui/icons-material/DarkMode";
import HistoryIcon from "@mui/icons-material/History";
import LightModeIcon from "@mui/icons-material/LightMode";
import PersonSearchIcon from "@mui/icons-material/PersonSearch";
import ShieldIcon from "@mui/icons-material/Shield";
import SpaceDashboardIcon from "@mui/icons-material/SpaceDashboard";
import {
  AppBar,
  Box,
  Button,
  Container,
  IconButton,
  Toolbar,
  Tooltip,
  Typography,
} from "@mui/material";
import { Link as RouterLink, Outlet, useLocation } from "react-router-dom";

import { useColorMode } from "../theme";

const NAV = [
  { to: "/", label: "Dashboard", icon: <SpaceDashboardIcon fontSize="small" /> },
  { to: "/search", label: "New Search", icon: <PersonSearchIcon fontSize="small" /> },
  { to: "/history", label: "History", icon: <HistoryIcon fontSize="small" /> },
];

export default function Layout() {
  const { mode, toggle } = useColorMode();
  const location = useLocation();

  return (
    <Box sx={{ minHeight: "100vh", display: "flex", flexDirection: "column" }}>
      <AppBar position="sticky" elevation={1} color="default">
        <Toolbar sx={{ gap: 2 }}>
          <ShieldIcon color="primary" />
          <Typography variant="h6" component={RouterLink} to="/" sx={{
            color: "inherit", textDecoration: "none", flexGrow: { xs: 1, sm: 0 }, mr: 2,
          }}>
            Adverse Intelligence
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
        </Toolbar>
      </AppBar>
      <Container maxWidth="lg" sx={{ py: 3, flexGrow: 1 }}>
        <Outlet />
      </Container>
      <Box component="footer" sx={{ py: 2, textAlign: "center", opacity: 0.6 }}>
        <Typography variant="caption">
          Adverse Intelligence Platform (MVP) — for legitimate business due diligence only.
        </Typography>
      </Box>
    </Box>
  );
}
