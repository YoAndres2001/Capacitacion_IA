/** Estructura principal: barra superior, navegación lateral y área de contenido. */

import {
  AccountCircle,
  Analytics,
  Apps,
  Brightness4,
  Brightness7,
  Dashboard,
  Logout,
  MenuBook,
  Menu as MenuIcon,
  People,
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
import { useState } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useColorMode } from '@/app/colorMode';
import { useAuth } from '@/features/auth/AuthContext';
import { NotificationCenter } from '@/shared/components/NotificationCenter';
import { ROLE_LABEL } from '@/shared/utils/format';

const DRAWER_WIDTH = 248;

interface NavItem {
  label: string;
  path: string;
  icon: React.ReactNode;
  requires?: 'content' | 'users';
}

const NAV_ITEMS: NavItem[] = [
  { label: 'Panel', path: '/admin', icon: <Dashboard />, requires: 'content' },
  { label: 'Proyectos', path: '/proyectos', icon: <Apps />, requires: 'content' },
  { label: 'Capacitaciones', path: '/capacitaciones', icon: <MenuBook />, requires: 'content' },
  { label: 'Usuarios', path: '/usuarios', icon: <People />, requires: 'users' },
  { label: 'Analítica', path: '/analitica', icon: <Analytics />, requires: 'users' },
  { label: 'Mis cursos', path: '/mis-cursos', icon: <School /> },
];

export function AppLayout() {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);

  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuth();
  const { mode, toggle } = useColorMode();

  const visibleItems = NAV_ITEMS.filter((item) => {
    if (item.requires === 'content') return user?.permissions.manage_content;
    if (item.requires === 'users') return user?.permissions.manage_users;
    return true;
  });

  const go = (path: string) => {
    navigate(path);
    if (isMobile) setDrawerOpen(false);
  };

  const drawerContent = (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <Toolbar sx={{ px: 2.5 }}>
        <School sx={{ mr: 1.5, color: 'primary.main' }} />
        <Box>
          <Typography variant="h5" sx={{ lineHeight: 1.1 }}>
            Capacita IA
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {user?.company?.name ?? 'Plataforma'}
          </Typography>
        </Box>
      </Toolbar>
      <Divider />
      <List sx={{ px: 1.5, py: 1, flex: 1 }}>
        {visibleItems.map((item) => {
          const selected =
            location.pathname === item.path || location.pathname.startsWith(`${item.path}/`);
          return (
            <ListItemButton
              key={item.path}
              selected={selected}
              onClick={() => go(item.path)}
              sx={{ borderRadius: 2, mb: 0.5 }}
            >
              <ListItemIcon sx={{ minWidth: 40, color: selected ? 'primary.main' : undefined }}>
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
      <Divider />
      <Box sx={{ p: 2 }}>
        <Typography variant="caption" color="text.secondary">
          IA local gratuita · Ollama
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
        <Toolbar>
          <IconButton
            edge="start"
            onClick={() => setDrawerOpen(true)}
            sx={{ mr: 2, display: { md: 'none' } }}
            aria-label="Abrir menú"
          >
            <MenuIcon />
          </IconButton>

          <Box sx={{ flexGrow: 1 }} />

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
          variant={isMobile ? 'temporary' : 'permanent'}
          open={isMobile ? drawerOpen : true}
          onClose={() => setDrawerOpen(false)}
          ModalProps={{ keepMounted: true }}
          sx={{
            '& .MuiDrawer-paper': {
              width: DRAWER_WIDTH,
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
          width: { md: `calc(100% - ${DRAWER_WIDTH}px)` },
          bgcolor: 'background.default',
          minHeight: '100vh',
        }}
      >
        <Toolbar />
        <Box sx={{ p: { xs: 2, md: 3 } }}>
          <Outlet />
        </Box>
      </Box>
    </Box>
  );
}
