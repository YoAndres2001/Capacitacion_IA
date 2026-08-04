/** Contexto de autenticación: sesión, permisos y ciclo de vida del JWT. */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { api, tokenStorage } from '@/shared/api/client';
import { endpoints } from '@/shared/api/endpoints';
import type { LoginResponse, Profile, Role } from '@/shared/api/types';

interface AuthContextValue {
  user: Profile | null;
  loading: boolean;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<Profile>;
  logout: () => Promise<void>;
  refreshProfile: () => Promise<void>;
  hasRole: (...roles: Role[]) => boolean;
  canManageContent: boolean;
  canManageUsers: boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);

  const loadProfile = useCallback(async () => {
    if (!tokenStorage.access) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const { data } = await api.get<Profile>(endpoints.auth.me);
      setUser(data);
    } catch {
      // El interceptor ya intentó refrescar: si llegamos aquí, la sesión murió.
      tokenStorage.clear();
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadProfile();
  }, [loadProfile]);

  const login = useCallback(async (email: string, password: string) => {
    const { data } = await api.post<LoginResponse>(endpoints.auth.login, { email, password });
    tokenStorage.set(data.access, data.refresh);
    setUser(data.user);
    return data.user;
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.post(endpoints.auth.logout, { refresh: tokenStorage.refresh });
    } catch {
      // Cerrar sesión localmente es lo importante; el backend expira el token igual.
    } finally {
      tokenStorage.clear();
      setUser(null);
    }
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      loading,
      isAuthenticated: user !== null,
      login,
      logout,
      refreshProfile: loadProfile,
      hasRole: (...roles: Role[]) => (user ? roles.includes(user.role) : false),
      canManageContent: user?.permissions.manage_content ?? false,
      canManageUsers: user?.permissions.manage_users ?? false,
    }),
    [user, loading, login, logout, loadProfile],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth debe usarse dentro de <AuthProvider>.');
  return context;
}
