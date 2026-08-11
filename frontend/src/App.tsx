import CssBaseline from '@mui/material/CssBaseline';
import { ThemeProvider } from '@mui/material/styles';
import { QueryClientProvider } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { BrowserRouter } from 'react-router-dom';
import { queryClient } from '@/app/queryClient';
import { AppRouter } from '@/app/router';
import { darkTheme, lightTheme } from '@/app/theme';
import { AuthProvider } from '@/features/auth/AuthContext';
import { ColorModeContext, type ColorMode } from '@/app/colorMode';
import { SnackbarProvider } from '@/shared/components/SnackbarProvider';

const MODE_KEY = 'nexora.colorMode';

export default function App() {
  // El modo oscuro es el predeterminado; solo se respeta la elección guardada.
  const [mode, setMode] = useState<ColorMode>(
    () => (localStorage.getItem(MODE_KEY) as ColorMode | null) ?? 'dark',
  );

  const colorMode = useMemo(
    () => ({
      mode,
      toggle: () =>
        setMode((previous) => {
          const next = previous === 'light' ? 'dark' : 'light';
          localStorage.setItem(MODE_KEY, next);
          return next;
        }),
    }),
    [mode],
  );

  const theme = mode === 'light' ? lightTheme : darkTheme;

  return (
    <ColorModeContext.Provider value={colorMode}>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <QueryClientProvider client={queryClient}>
          <SnackbarProvider>
            <BrowserRouter>
              <AuthProvider>
                <AppRouter />
              </AuthProvider>
            </BrowserRouter>
          </SnackbarProvider>
        </QueryClientProvider>
      </ThemeProvider>
    </ColorModeContext.Provider>
  );
}
