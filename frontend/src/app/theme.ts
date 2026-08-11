import { createTheme, type ThemeOptions } from '@mui/material/styles';
import { esES } from '@mui/material/locale';

/**
 * Puntos de corte de la plataforma.
 *
 * Se redefinen los de MUI para que coincidan exactamente con los cuatro tipos
 * de pantalla que debe soportar el sistema. Los valores son el borde inferior
 * de cada rango, de modo que `down`/`up`/`between` de MUI producen justo las
 * mismas media queries que hay en `index.css`:
 *
 *   xs → teléfonos          (             …  749 px)  breakpoints.down('sm')
 *   sm → tabletas           (  750 px … 1024 px)      breakpoints.between('sm', 'md')
 *   md → notebooks          ( 1025 px … 1366 px)      breakpoints.between('md', 'lg')
 *   lg → monitores          ( 1367 px … 1919 px)      breakpoints.between('lg', 'xl')
 *   xl → monitores grandes  ( 1920 px …        )      breakpoints.up('xl')
 *
 * `xl` no estaba en el pedido: se agrega porque MUI exige cinco claves y porque
 * permite aprovechar los monitores anchos sin estirar el contenido.
 */
export const BREAKPOINTS = {
  xs: 0,
  sm: 750,
  md: 1025,
  lg: 1367,
  xl: 1920,
} as const;

/** Media query cruda: la tipografía se define antes de existir el tema. */
const up = (px: number) => `@media (min-width:${px}px)`;

const shared: ThemeOptions = {
  breakpoints: { values: { ...BREAKPOINTS } },
  typography: {
    fontFamily: '"Inter", -apple-system, "Segoe UI", Roboto, sans-serif',
    // Los títulos escalan con la pantalla: en un teléfono un h1 de 2rem come
    // media pantalla y obliga a cortar palabras.
    h1: {
      fontSize: '1.5rem',
      fontWeight: 700,
      letterSpacing: '-0.02em',
      [up(BREAKPOINTS.sm)]: { fontSize: '1.75rem' },
      [up(BREAKPOINTS.md)]: { fontSize: '2rem' },
    },
    h2: {
      fontSize: '1.3rem',
      fontWeight: 700,
      letterSpacing: '-0.015em',
      [up(BREAKPOINTS.sm)]: { fontSize: '1.45rem' },
      [up(BREAKPOINTS.md)]: { fontSize: '1.6rem' },
    },
    h3: {
      fontSize: '1.15rem',
      fontWeight: 600,
      [up(BREAKPOINTS.sm)]: { fontSize: '1.22rem' },
      [up(BREAKPOINTS.md)]: { fontSize: '1.3rem' },
    },
    h4: {
      fontSize: '1.05rem',
      fontWeight: 600,
      [up(BREAKPOINTS.md)]: { fontSize: '1.15rem' },
    },
    h5: { fontSize: '1rem', fontWeight: 600 },
    h6: { fontSize: '0.95rem', fontWeight: 600 },
    button: { textTransform: 'none', fontWeight: 600 },
  },
  shape: { borderRadius: 10 },
  components: {
    // Sin SSR el hook resuelve en el primer render: evita el parpadeo de layout
    // al montar componentes que dependen del tamaño (cajón, chat, sidebar).
    MuiUseMediaQuery: {
      defaultProps: { noSsr: true },
    },
    MuiButton: {
      defaultProps: { disableElevation: true },
      styleOverrides: {
        root: ({ theme }) => ({
          borderRadius: 8,
          paddingInline: 18,
          [theme.breakpoints.down('sm')]: { paddingInline: 12 },
        }),
      },
    },
    MuiCard: {
      styleOverrides: { root: { borderRadius: 14 } },
    },
    MuiPaper: {
      styleOverrides: { rounded: { borderRadius: 14 } },
    },
    MuiChip: {
      styleOverrides: { root: { fontWeight: 600, maxWidth: '100%' } },
    },
    MuiTextField: {
      defaultProps: { size: 'small', fullWidth: true },
    },
    MuiTooltip: {
      defaultProps: { arrow: true },
    },
    // Las pestañas se desbordan en teléfonos: por defecto se desplazan.
    // Quien necesite otro comportamiento (el reproductor usa `fullWidth`) lo
    // sigue declarando en su propia instancia.
    MuiTabs: {
      defaultProps: {
        variant: 'scrollable',
        scrollButtons: 'auto',
        allowScrollButtonsMobile: true,
      },
    },
    // En teléfonos el diálogo ocupa casi toda la pantalla en vez de quedar
    // encajonado con márgenes de escritorio.
    MuiDialog: {
      styleOverrides: {
        paper: ({ theme }) => ({
          [theme.breakpoints.down('sm')]: {
            margin: 12,
            width: 'calc(100% - 24px)',
            maxWidth: 'calc(100% - 24px)',
            maxHeight: 'calc(100% - 24px)',
          },
        }),
      },
    },
    MuiDialogTitle: {
      styleOverrides: {
        root: ({ theme }) => ({
          [theme.breakpoints.down('sm')]: { paddingInline: 16 },
        }),
      },
    },
    MuiDialogContent: {
      styleOverrides: {
        root: ({ theme }) => ({
          [theme.breakpoints.down('sm')]: { paddingInline: 16 },
        }),
      },
    },
    MuiDialogActions: {
      styleOverrides: {
        root: ({ theme }) => ({
          [theme.breakpoints.down('sm')]: { paddingInline: 16 },
        }),
      },
    },
    // Las tablas se desplazan horizontalmente dentro de su contenedor; aquí
    // solo se recupera ancho recortando el relleno de cada celda.
    MuiTableCell: {
      styleOverrides: {
        root: ({ theme }) => ({
          [theme.breakpoints.down('sm')]: { paddingInline: 8 },
        }),
      },
    },
    // Objetivo táctil mínimo cómodo en teléfonos y tabletas.
    MuiIconButton: {
      styleOverrides: {
        root: ({ theme }) => ({
          [theme.breakpoints.down('md')]: { minWidth: 40, minHeight: 40 },
        }),
      },
    },
    MuiListItemButton: {
      styleOverrides: {
        root: ({ theme }) => ({
          [theme.breakpoints.down('md')]: { minHeight: 44 },
        }),
      },
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
