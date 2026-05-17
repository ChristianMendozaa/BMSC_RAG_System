'use client';

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from 'react';
import { useRouter } from 'next/navigation';
import { getMe } from './api';
import type { UserInfo } from './api';

interface AuthContextValue {
  user: UserInfo | null;
  isLoading: boolean;
  isAdmin: boolean;
  canManageUsers: boolean;
  canManageCollections: boolean;
  canUploadDocuments: boolean;
  canDeleteDocuments: boolean;
  refetch: () => Promise<void>;
  clearAuth: () => void;
}

const AuthContext = createContext<AuthContextValue>({
  user: null,
  isLoading: true,
  isAdmin: false,
  canManageUsers: false,
  canManageCollections: false,
  canUploadDocuments: false,
  canDeleteDocuments: false,
  refetch: async () => {},
  clearAuth: () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<UserInfo | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const clearAuth = useCallback(() => {
    if (typeof window !== 'undefined') {
      localStorage.removeItem('access_token');
    }
    setUser(null);
  }, []);

  const fetchUser = useCallback(async () => {
    const token =
      typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;

    if (!token) {
      setIsLoading(false);
      setUser(null);
      return;
    }

    try {
      const me = await getMe();
      setUser(me);
    } catch {
      // Token inválido o expirado
      clearAuth();
      router.push('/login');
    } finally {
      setIsLoading(false);
    }
  }, [clearAuth, router]);

  useEffect(() => {
    fetchUser();
  }, [fetchUser]);

  // Re-validar permisos cuando el usuario vuelve a la pestaña
  useEffect(() => {
    const handleFocus = () => {
      const token =
        typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
      if (token) fetchUser();
    };
    window.addEventListener('focus', handleFocus);
    return () => window.removeEventListener('focus', handleFocus);
  }, [fetchUser]);

  const role = user?.role;

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        isAdmin: !!(
          role?.can_manage_users ||
          role?.can_manage_collections ||
          role?.can_upload_documents ||
          role?.can_delete_documents
        ),
        canManageUsers: !!role?.can_manage_users,
        canManageCollections: !!role?.can_manage_collections,
        canUploadDocuments: !!role?.can_upload_documents,
        canDeleteDocuments: !!role?.can_delete_documents,
        refetch: fetchUser,
        clearAuth,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
