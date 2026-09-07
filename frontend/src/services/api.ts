import axios from 'axios';
import AsyncStorage from '@react-native-async-storage/async-storage';

const API_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';

const api = axios.create({
  baseURL: `${API_URL}/api`,
  headers: { 'Content-Type': 'application/json' },
  timeout: 10000,
});

api.interceptors.request.use(async (config) => {
  const token = await AsyncStorage.getItem('auth_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      AsyncStorage.removeItem('auth_token');
    }
    return Promise.reject(error);
  }
);

export const authAPI = {
  register: (data: any) => api.post('/auth/register', data),
  login: (data: any) => api.post('/auth/login', data),
  getMe: () => api.get('/auth/me'),
  updateProfile: (data: any) => api.put('/auth/profile', data),
};

export const screensAPI = {
  list: (params?: any) => api.get('/screens', { params }),
  getCities: () => api.get('/screens/cities'),
  get: (id: string) => api.get(`/screens/${id}`),
  calculatePrice: (id: string, schedule: any) => api.post(`/screens/${id}/calculate-price`, schedule),
};

export const campaignsAPI = {
  create: (data: any) => api.post('/campaigns', data),
  list: (params?: any) => api.get('/campaigns', { params }),
  get: (id: string) => api.get(`/campaigns/${id}`),
  update: (id: string, data: any) => api.put(`/campaigns/${id}`, data),
  delete: (id: string) => api.delete(`/campaigns/${id}`),
};

export const mediaAPI = {
  upload: (data: any) => api.post('/media/upload', data),
  list: () => api.get('/media'),
  get: (id: string) => api.get(`/media/${id}`),
  delete: (id: string) => api.delete(`/media/${id}`),
};

export const paymentsAPI = {
  create: (data: any) => api.post('/payments', data),
  list: () => api.get('/payments'),
  get: (id: string) => api.get(`/payments/${id}`),
};

export const adminAPI = {
  listUsers: () => api.get('/admin/users'),
  updateUser: (id: string, active: boolean) => api.put(`/admin/users/${id}?active=${active}`),
  listCampaigns: (params?: any) => api.get('/admin/campaigns', { params }),
  approveCampaign: (id: string) => api.put(`/admin/campaigns/${id}/approve`),
  rejectCampaign: (id: string, notes?: string) =>
    api.put(`/admin/campaigns/${id}/reject${notes ? '?notes=' + encodeURIComponent(notes) : ''}`),
  createScreen: (data: any) => api.post('/admin/screens', data),
  updateScreen: (id: string, data: any) => api.put(`/admin/screens/${id}`, data),
  deleteScreen: (id: string) => api.delete(`/admin/screens/${id}`),
  analytics: () => api.get('/admin/analytics'),
};

// Devices (Player App)
export const devicesAPI = {
  register: (data: any) => api.post('/devices/register', data),
  check: (deviceId: string) => api.get(`/devices/${deviceId}/check`),
  heartbeat: (deviceId: string, data: any) => api.post(`/devices/${deviceId}/heartbeat`, data),
  playlist: (deviceId: string) => api.get(`/devices/${deviceId}/playlist`),
};

// Admin Devices
export const adminDevicesAPI = {
  list: () => api.get('/admin/devices'),
  activate: (data: any) => api.post('/admin/devices/activate', data),
  remove: (deviceId: string) => api.delete(`/admin/devices/${deviceId}`),
  reassign: (deviceId: string, screenId: string) =>
    api.put(`/admin/devices/${deviceId}/reassign?screen_id=${screenId}`),
};

export const analyticsAPI = {
  dashboard: () => api.get('/analytics/dashboard'),
};

// Phase 2C P1: Plans API (public, no auth required)
export const plansAPI = {
  listPublic: () => api.get('/plans'),
};

// Phase 2C P1: Customer self-signup
export const signupAPI = {
  customerSignup: (data: {
    plan_id: string;
    billing_cycle?: 'monthly' | 'annual';
    logo_filename?: string;
    logo_base64?: string;
    business_name: string;
    contact_name: string;
    contact_email: string;
    contact_phone?: string | null;
    password: string;
    org_name?: string;
  }) => api.post('/auth/customer-signup', data),
};

// Phase 2C P1: Customer Workspace API (auth required, org-scoped)
export const orgBrandingAPI = {
  uploadLogo: (logo_filename: string, logo_base64: string) =>
    api.post('/workspace/logo', { logo_filename, logo_base64 }),
  removeLogo: () => api.delete('/workspace/logo'),
};

export const clientLogosAPI = {
  listPublic: () => api.get('/client-logos'),
};

export type TeamRole = 'admin' | 'manager' | 'employee';

export const teamAPI = {
  list: () => api.get('/workspace/team'),
  create: (data: { name: string; email: string; temporary_password: string; role: TeamRole }) =>
    api.post('/workspace/team', data),
  update: (id: string, data: { role?: TeamRole; active?: boolean }) =>
    api.patch(`/workspace/team/${id}`, data),
  resetPassword: (id: string, temporary_password: string) =>
    api.post(`/workspace/team/${id}/reset-password`, { temporary_password }),
  deactivate: (id: string) => api.delete(`/workspace/team/${id}`),
  changeMyPassword: (current_password: string, new_password: string) =>
    api.post('/workspace/change-password', { current_password, new_password }),
};

export const workspaceAPI = {
  context: () => api.get('/workspace/context'),
  // Screens
  screens: () => api.get('/workspace/screens'),
  createScreen: (data: { name: string; location?: string }) => api.post('/workspace/screens', data),
  connectScreen: (data: { activation_code: string; screen_name: string }) =>
    api.post('/workspace/screens/connect', data),
  // Devices
  devices: () => api.get('/workspace/devices'),
  // Media
  media: () => api.get('/workspace/media'),
  uploadMedia: (data: { filename: string; content_type: string; data: string }) =>
    api.post('/media/upload', data, { timeout: 120000 }),
  // Menus
  menus: () => api.get('/workspace/menus'),
  getMenu: (id: string) => api.get(`/workspace/menus/${id}`),
  createMenu: (data: { name: string; description?: string; items?: any[]; source?: string }) =>
    api.post('/workspace/menus', data),
  updateMenu: (id: string, data: { name?: string; description?: string }) =>
    api.put(`/workspace/menus/${id}`, data),
  deleteMenu: (id: string) => api.delete(`/workspace/menus/${id}`),
  addMenuItem: (menuId: string, item: {
    name: string; price: number; description?: string; category?: string;
    available?: boolean; media_id?: string; image_url?: string;
  }) => api.post(`/workspace/menus/${menuId}/items`, item),
  updateMenuItem: (menuId: string, itemId: string, item: Partial<{
    name: string; price: number; description: string; category: string;
    available: boolean; media_id: string; image_url: string;
  }>) => api.put(`/workspace/menus/${menuId}/items/${itemId}`, item),
  deleteMenuItem: (menuId: string, itemId: string) =>
    api.delete(`/workspace/menus/${menuId}/items/${itemId}`),
  publishMenu: (menuId: string, data?: { screen_ids?: string[] }) =>
    api.post(`/workspace/menus/${menuId}/publish`, data || {}),
  // Billing
  billing: () => api.get('/workspace/billing'),
  screenCostPreview: (additionalScreens: number) =>
    api.get(`/workspace/billing/screen-cost?additional_screens=${additionalScreens}`),
  addScreens: (additionalScreens: number) =>
    api.post('/workspace/billing/add-screens', { additional_screens: additionalScreens }),
  // Playlists
  playlists: () => api.get('/workspace/playlists'),
  createPlaylist: (data: {
    name: string; description?: string;
    items: { type: 'media' | 'menu'; ref_id: string; title?: string; duration?: number }[];
  }) => api.post('/workspace/playlists', data),
  publishPlaylist: (id: string, screen_ids?: string[]) =>
    api.post(`/workspace/playlists/${id}/publish`, { screen_ids: screen_ids || [] }),
  updatePlaylist: (id: string, data: {
    name?: string;
    items?: { type: 'media' | 'menu'; ref_id: string; title?: string; duration?: number }[];
  }) => api.patch(`/workspace/playlists/${id}`, data),
  deletePlaylist: (id: string) => api.delete(`/workspace/playlists/${id}`),
  activity: (limit = 60) => api.get(`/workspace/activity?limit=${limit}`),
  nowPlaying: () => api.get('/workspace/now-playing'),
  weeklyReport: (weeksAgo = 0) => api.get(`/workspace/reports/weekly?weeks_ago=${weeksAgo}`),
  activePromos: () => api.get('/workspace/promos/active'),
  launchPromo: (data: {
    kind: 'image' | 'text'; text?: string; subtitle?: string; media_id?: string;
    duration_minutes?: number | null; screen_ids?: string[]; item_seconds?: number;
  }) => api.post('/workspace/promos', data, { timeout: 60000 }),
  stopPromo: (id: string) => api.delete(`/workspace/promos/${id}`),
  aiPhotoForItem: (menuId: string, itemId: string) =>
    api.post(`/workspace/menus/${menuId}/items/${itemId}/ai-photo`, {}, { timeout: 180000 }),
  aiImportMenu: (data: { image_base64: string; content_type: string }) =>
    api.post('/workspace/menus/ai-import', data, { timeout: 180000 }),
  schedules: () => api.get('/workspace/schedules'),
  users: () => api.get('/workspace/users'),
};

// Player simulator API (no auth, device_id is the token)
export const playerAPI = {
  register: (data?: { device_name?: string }) => api.post('/devices/register', data || {}),
  check: (deviceId: string) => api.get(`/devices/${deviceId}/check`),
  content: (deviceId: string) => api.get(`/workspace/player/${deviceId}/content`),
};

export default api;
