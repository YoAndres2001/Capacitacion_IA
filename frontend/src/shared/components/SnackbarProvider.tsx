/** Notificaciones tipo toast, disponibles en toda la aplicación. */

import { Alert, Snackbar, useMediaQuery, useTheme } from '@mui/material';
import type { AlertColor } from '@mui/material';
import { createContext, useCallback, useContext, useMemo, useState } from 'react';
import type { ReactNode } from 'react';

interface Toast {
  message: string;
  severity: AlertColor;
}

interface SnackbarContextValue {
  notify: (message: string, severity?: AlertColor) => void;
  success: (message: string) => void;
  error: (message: string) => void;
  info: (message: string) => void;
  warning: (message: string) => void;
}

const SnackbarContext = createContext<SnackbarContextValue | null>(null);

export function SnackbarProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<Toast | null>(null);
  const theme = useTheme();
  const isPhone = useMediaQuery(theme.breakpoints.down('sm'));

  const notify = useCallback((message: string, severity: AlertColor = 'info') => {
    setToast({ message, severity });
  }, []);

  const value = useMemo<SnackbarContextValue>(
    () => ({
      notify,
      success: (message) => notify(message, 'success'),
      error: (message) => notify(message, 'error'),
      info: (message) => notify(message, 'info'),
      warning: (message) => notify(message, 'warning'),
    }),
    [notify],
  );

  return (
    <SnackbarContext.Provider value={value}>
      {children}
      <Snackbar
        open={toast !== null}
        autoHideDuration={toast?.severity === 'error' ? 8000 : 4000}
        onClose={() => setToast(null)}
        // En teléfono el aviso va centrado y arriba: abajo a la derecha choca
        // con el pulgar y con la barra gestual del sistema.
        anchorOrigin={
          isPhone
            ? { vertical: 'top', horizontal: 'center' }
            : { vertical: 'bottom', horizontal: 'right' }
        }
        sx={isPhone ? { left: 12, right: 12 } : undefined}
      >
        <Alert
          onClose={() => setToast(null)}
          severity={toast?.severity ?? 'info'}
          variant="filled"
          sx={{ width: { xs: '100%', sm: 'auto' }, maxWidth: 480 }}
        >
          {toast?.message}
        </Alert>
      </Snackbar>
    </SnackbarContext.Provider>
  );
}

export function useSnackbar(): SnackbarContextValue {
  const context = useContext(SnackbarContext);
  if (!context) throw new Error('useSnackbar debe usarse dentro de <SnackbarProvider>.');
  return context;
}
