import { CssBaseline, ThemeProvider, createTheme } from "@mui/material";
import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

type Mode = "light" | "dark";

const ColorModeContext = createContext<{ mode: Mode; toggle: () => void }>({
  mode: "light",
  toggle: () => {},
});

export const useColorMode = () => useContext(ColorModeContext);

function buildTheme(mode: Mode) {
  return createTheme({
    palette: {
      mode,
      primary: { main: mode === "light" ? "#14324f" : "#7da7d9" },
      secondary: { main: "#b3541e" },
    },
    shape: { borderRadius: 8 },
    typography: {
      fontFamily: '"Source Sans 3", "Segoe UI", Arial, sans-serif',
      h5: { fontWeight: 700 },
      h6: { fontWeight: 600 },
    },
  });
}

export function AppThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<Mode>(() => {
    const stored = localStorage.getItem("aip-color-mode");
    if (stored === "light" || stored === "dark") return stored;
    return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  });

  useEffect(() => {
    localStorage.setItem("aip-color-mode", mode);
  }, [mode]);

  const value = useMemo(
    () => ({ mode, toggle: () => setMode((m) => (m === "light" ? "dark" : "light")) }),
    [mode],
  );
  const theme = useMemo(() => buildTheme(mode), [mode]);

  return (
    <ColorModeContext.Provider value={value}>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        {children}
      </ThemeProvider>
    </ColorModeContext.Provider>
  );
}
