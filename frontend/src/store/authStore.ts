import { create } from 'zustand';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { authAPI } from '../services/api';
import type { User } from '../types';

interface AuthState {
  token: string | null;
  user: User | null;
  isLoading: boolean;
  isInitialized: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (name: string, email: string, password: string, company_name?: string) => Promise<void>;
  logout: () => Promise<void>;
  initialize: () => Promise<void>;
  setUser: (user: User) => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  token: null,
  user: null,
  isLoading: false,
  isInitialized: false,

  login: async (email, password) => {
    set({ isLoading: true });
    try {
      const res = await authAPI.login({ email, password });
      const { access_token, user } = res.data;
      await AsyncStorage.setItem('auth_token', access_token);
      set({ token: access_token, user, isLoading: false });
    } catch (error: any) {
      set({ isLoading: false });
      throw new Error(error.response?.data?.detail || 'Login failed');
    }
  },

  register: async (name, email, password, company_name) => {
    set({ isLoading: true });
    try {
      const res = await authAPI.register({ name, email, password, company_name });
      const { access_token, user } = res.data;
      await AsyncStorage.setItem('auth_token', access_token);
      set({ token: access_token, user, isLoading: false });
    } catch (error: any) {
      set({ isLoading: false });
      throw new Error(error.response?.data?.detail || 'Registration failed');
    }
  },

  logout: async () => {
    await AsyncStorage.removeItem('auth_token');
    set({ token: null, user: null });
  },

  initialize: async () => {
    try {
      const token = await AsyncStorage.getItem('auth_token');
      if (token) {
        const res = await authAPI.getMe();
        // Phase 2C: getMe returns rbac_role and organization_id
        set({ token, user: res.data, isInitialized: true });
      } else {
        set({ isInitialized: true });
      }
    } catch {
      await AsyncStorage.removeItem('auth_token');
      set({ token: null, user: null, isInitialized: true });
    }
  },

  setUser: (user) => set({ user }),
}));

// Helpers
export const isWorkspaceUser = (user: User | null): boolean =>
  user?.rbac_role === 'SELF_SERVICE_OWNER' || user?.rbac_role === 'SELF_SERVICE_MANAGER';

export const isAdminUser = (user: User | null): boolean =>
  user?.role === 'admin' || user?.rbac_role === 'SUPER_ADMIN' || user?.rbac_role === 'MEDIAVIEW_ADMIN';
