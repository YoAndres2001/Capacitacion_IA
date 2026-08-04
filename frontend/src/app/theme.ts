import { createTheme, type ThemeOptions } from '@mui/material/styles';
import { esES } from '@mui/material/locale';

const shared: ThemeOptions = {
  typography: {
    fontFamily: '"Inter", -apple-system, "Segoe UI", Roboto, sans-serif',
    h1: { fontSize: '2rem', fontWeight: 700, letterSpacing: '-0.02em' },
    h2: { fontSize: '1.6rem', fontWeight: 700, letterSpacing: '-0.015em' },
    h3: { fontSize: '1.3rem', fontWeight: 600 },
    h4: { fontSize: '1.15rem', fontWeight: 600 },
    h5: { fontSize: '1rem', fontWeight: 600 },
    h6: { fontSize: '0.95rem', fontWeight: 600 },
    button: { textTransform: 'none', fontWeight: 600 },
  },
  shape: { borderRadius: 10 },
  components: {
    MuiButton: {
      defaultProps: { disableElevation: true },
      styleOverrides: { root: { borderRadius: 8, paddingInline: 18 } },
    },
    MuiCard: {
      styleOverrides: { root: { borderRadius: 14 } },
    },
    MuiPaper: {
      styleOverrides: { rounded: { borderRadius: 14 } },
    },
    MuiChip: {
      styleOverrides: { root: { fontWeight: 600 } },
    },
    MuiTextField: {
      defaultProps: { size: 'small', fullWidth: true },
    },
    MuiTooltip: {
      defaultProps: { arrow: true },
    },
  },
};

export const lightTheme = createTheme(
  {
    ...shared,
    palette: {
      mode: 'light',
      primary: { main: '#1565c0' },
      secondary: { main: '#7b1fa2' },
      success: { main: '#2e7d32' },
      warning: { main: '#ed6c02' },
      error: { main: '#c62828' },
      info: { main: '#0277bd' },
      background: { default: '#f4f6f9', paper: '#ffffff' },
    },
  },
  esES,
);

export const darkTheme = createTheme(
  {
    ...shared,
    palette: {
      mode: 'dark',
      primary: { main: '#64b5f6' },
      secondary: { main: '#ce93d8' },
      success: { main: '#66bb6a' },
      warning: { main: '#ffa726' },
      error: { main: '#ef5350' },
      info: { main: '#4fc3f7' },
      background: { default: '#0f1419', paper: '#161c24' },
    },
  },
  esES,
);

/** Colores por estado de material, compartidos por chips y barras de progreso. */
export const statusColor = {
  PENDING: 'default',
  PROCESSING: 'info',
  ANALYZING: 'warning',
  AVAILABLE: 'success',
  ERROR: 'error',
} as const;

export const trainingStatusColor = {
  DRAFT: 'default',
  PUBLISHED: 'success',
  ARCHIVED: 'warning',
} as const;
