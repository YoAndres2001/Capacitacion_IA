/** Estructura principal: barra superior, navegación lateral y área de contenido. */

import {
  AccountCircle,
  Analytics,
  Apps,
  Brightness4,
  Brightness7,
  Dashboard,
  Home,
  Insights,
  Logout,
  MenuBook,
  Menu as MenuIcon,
  People,
  Route as RouteIcon,
  School,
} from '@mui/icons-material';
import {
  AppBar,
  Avatar,
  Box,
  Divider,
  Drawer,
  IconButton,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Menu,
  MenuItem,
  Toolbar,
  Tooltip,
  Typography,
  useMediaQuery,
  useTheme,
} from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useColorMode } from '@/app/colorMode';
import { useAuth } from '@/features/auth/AuthContext';
import { api } from '@/shared/api/client';
import { endpoints } from '@/shared/api/endpoints';
import type { AIHealth } from '@/shared/api/types';
import { CompanyLogo } from '@/shared/components/CompanyLogo';
import { NotificationCenter } from '@/shared/components/NotificationCenter';
import { ROLE_LABEL } from '@/shared/utils/format';

const DRAWER_WIDTH = 248;

/**
 * Ancho del cajón cuando se abre por encima del contenido (teléfonos y
 * tabletas). En un teléfono de 360 px un cajón de 248 px deja apenas 112 px
 * de contexto detrás; el `min` con `85vw` evita que tape la pantalla entera
 * en los equipos más angostos.
 */
const TEMP_DRAWER_WIDTH = 'min(280px, 85vw)';

interface NavItem {
  label: string;
  path: string;
  icon: React.ReactNode;
  requires?: 'content' | 'users';
}

interface NavGroup {
  /** Título de la sección; sin título los ítems van sueltos arriba del menú. */
  title?: string;
  items: NavItem[];
}

const NAV_GROUPS: NavGroup[] = [
  {
    items: [
      { label: 'Inicio', path: '/inicio', icon: <Home /> },
      { label: 'Academia', path: '/academia', icon: <School /> },
    ],
  },
  {
    title: 'Tu progreso',
    items: [
      { label: 'Rutas', path: '/rutas', icon: <RouteIcon /> },
      { label: 'Progreso', path: '/progreso', icon: <Insights /> },
    ],
  },
  {
    title: 'Gestión',
    items: [
      { label: 'Panel', path: '/admin', icon: <Dashboard />, requires: 'content' },
      { label: 'Proyectos', path: '/proyectos', icon: <Apps />, requires: 'content' },
      { label: 'Capacitaciones', path: '/capacitaciones', icon: <MenuBook />, requires: 'content' },
      { label: 'Usuarios', path: '/usuarios', icon: <People />, requires: 'users' },
      { label: 'Analítica', path: '/analitica', icon: <Analytics />, requires: 'users' },
    ],
  },
];

export function AppLayout() {
  const theme = useTheme();
  // Teléfonos y tabletas (< 1025 px): el cajón se superpone al contenido. A
  // partir de notebook queda fijo, que es donde sobra ancho para las dos cosas.
  const isCompact = useMediaQuery(theme.breakpoints.down('md'));
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);

  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuth();
  const { mode, toggle } = useColorMode();

  const health = useQuery({
    queryKey: ['ai', 'health'],
    queryFn: async () => (await api.get<AIHealth>(endpoints.ai.health)).data,
    retry: false,
    staleTime: 300_000,
  });

  const visibleGroups = NAV_GROUPS.map((group) => ({
    ...group,
    items: group.items.filter((item) => {
      if (item.requires === 'content') return user?.permissions.manage_content;
      if (item.requires === 'users') return user?.permissions.manage_users;
      return true;
    }),
  })).filter((group) => group.items.length > 0);

  const go = (path: string) => {
    navigate(path);
    if (isCompact) setDrawerOpen(false);
  };

  const drawerContent = (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <Toolbar sx={{ px: 2.5 }}>
        <CompanyLogo companyName={user?.company?.name} />
      </Toolbar>
      <Divider />
      <Box sx={{ px: 1.5, py: 1, flex: 1, overflowY: 'auto' }}>
        {visibleGroups.map((group) => (
          <Box key={group.title ?? 'principal'} sx={{ mb: 1 }}>
            {group.title && (
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{
                  display: 'block',
                  px: 2,
                  pt: 1.5,
                  pb: 0.5,
                  fontWeight: 700,
                  letterSpacing: '0.08em',
                  textTransform: 'uppercase',
                }}
              >
                {group.title}
              </Typography>
            )}
            <List disablePadding>
              {group.items.map((item) => {
                const selected =
                  location.pathname === item.path || location.pathname.startsWith(`${item.path}/`);
                return (
                  <ListItemButton
                    key={item.path}
                    selected={selected}
                    onClick={() => go(item.path)}
                    sx={{ borderRadius: 2, mb: 0.5 }}
                  >
                    <ListItemIcon
                      sx={{ minWidth: 40, color: selected ? 'primary.main' : undefined }}
                    >
                      {item.icon}
                    </ListItemIcon>
                    <ListItemText
                      primary={item.label}
                      primaryTypographyProps={{ fontWeight: selected ? 600 : 500, fontSize: 14 }}
                    />
                  </ListItemButton>
                );
              })}
            </List>
          </Box>
        ))}
      </Box>
      <Divider />
      <Box sx={{ p: 2 }}>
        <Typography variant="caption" color="text.secondary">
          {health.data ? `IA · ${health.data.provider} · ${health.data.llm_model}` : 'IA'}
        </Typography>
      </Box>
    </Box>
  );

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh' }}>
      <AppBar
        position="fixed"
        color="inherit"
        elevation={0}
        sx={{
          width: { md: `calc(100% - ${DRAWER_WIDTH}px)` },
          ml: { md: `${DRAWER_WIDTH}px` },
          borderBottom: 1,
          borderColor: 'divider',
          backdropFilter: 'blur(8px)',
        }}
      >
        <Toolbar sx={{ px: { xs: 1, sm: 2, md: 3 }, gap: 0.5 }}>
          <IconButton
            edge="start"
            onClick={() => setDrawerOpen(true)}
            sx={{ mr: { xs: 0.5, sm: 1.5 }, display: { md: 'none' } }}
            aria-label="Abrir menú"
          >
            <MenuIcon />
          </IconButton>

          {/* Con el cajón oculto la barra se queda sin marca: se repone aquí. */}
          <Box sx={{ display: { xs: 'flex', md: 'none' }, minWidth: 0, flex: 1 }}>
            <CompanyLogo companyName={user?.company?.name} />
          </Box>

          <Box sx={{ flexGrow: 1, display: { xs: 'none', md: 'block' } }} />

          <Tooltip title={mode === 'light' ? 'Modo oscuro' : 'Modo claro'}>
            <IconButton onClick={toggle} aria-label="Cambiar tema">
              {mode === 'light' ? <Brightness4 /> : <Brightness7 />}
            </IconButton>
          </Tooltip>

          <NotificationCenter />

          <Tooltip title={user?.full_name ?? ''}>
            <IconButton onClick={(event) => setAnchorEl(event.currentTarget)} sx={{ ml: 0.5 }}>
              <Avatar sx={{ width: 34, height: 34, bgcolor: 'primary.main', fontSize: 15 }}>
                {user?.first_name?.[0]?.toUpperCase() ?? '?'}
              </Avatar>
            </IconButton>
          </Tooltip>

          <Menu
            anchorEl={anchorEl}
            open={Boolean(anchorEl)}
            onClose={() => setAnchorEl(null)}
            anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
            transformOrigin={{ vertical: 'top', horizontal: 'right' }}
          >
            <Box sx={{ px: 2, py: 1.5, minWidth: 220 }}>
              <Typography variant="subtitle2">{user?.full_name}</Typography>
              <Typography variant="caption" color="text.secondary" display="block">
                {user?.email}
              </Typography>
              <Typography variant="caption" color="primary.main">
                {ROLE_LABEL[user?.role ?? ''] ?? user?.role}
              </Typography>
            </Box>
            <Divider />
            <MenuItem
              onClick={() => {
                setAnchorEl(null);
                navigate('/perfil');
              }}
            >
              <ListItemIcon>
                <AccountCircle fontSize="small" />
              </ListItemIcon>
              Mi perfil
            </MenuItem>
            <MenuItem
              onClick={async () => {
                setAnchorEl(null);
                await logout();
                navigate('/login');
              }}
            >
              <ListItemIcon>
                <Logout fontSize="small" />
              </ListItemIcon>
              Cerrar sesión
            </MenuItem>
          </Menu>
        </Toolbar>
      </AppBar>

      <Box component="nav" sx={{ width: { md: DRAWER_WIDTH }, flexShrink: { md: 0 } }}>
        <Drawer
          variant={isCompact ? 'temporary' : 'permanent'}
          open={isCompact ? drawerOpen : true}
          onClose={() => setDrawerOpen(false)}
          // `keepMounted` mantiene el menú en el DOM: en móvil abrir el cajón
          // debe ser instantáneo, no volver a montar toda la navegación.
          ModalProps={{ keepMounted: true }}
          sx={{
            '& .MuiDrawer-paper': {
              width: isCompact ? TEMP_DRAWER_WIDTH : DRAWER_WIDTH,
              boxSizing: 'border-box',
              borderRight: 1,
              borderColor: 'divider',
            },
          }}
        >
          {drawerContent}
        </Drawer>
      </Box>

      <Box
        component="main"
        sx={{
          flexGrow: 1,
          // `minWidth: 0` es lo que permite que un hijo ancho (tabla, gráfico)
          // se desplace dentro de su caja en vez de estirar el layout flex.
          minWidth: 0,
          width: { md: `calc(100% - ${DRAWER_WIDTH}px)` },
          bgcolor: 'background.default',
          minHeight: '100vh',
        }}
      >
        <Toolbar />
        <Box
          sx={{
            // Los márgenes y el ancho máximo salen de las media queries de
            // `index.css`, así los cuatro tamaños se ajustan en un solo lugar.
            width: '100%',
            maxWidth: 'var(--app-max-width)',
            mx: 'auto',
            pt: 'var(--app-gutter)',
            pb: 'calc(var(--app-gutter) + var(--app-safe-bottom))',
            pl: 'calc(var(--app-gutter) + var(--app-safe-left))',
            pr: 'calc(var(--app-gutter) + var(--app-safe-right))',
          }}
        >
          <Outlet />
        </Box>
      </Box>
    </Box>
  );
}
