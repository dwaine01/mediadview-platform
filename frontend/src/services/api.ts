import axios from 'axios';
import AsyncStorage from '@react-native-async-storage/async-storage';

const API_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';

const api = axios.create({
  baseURL: `${API_URL}/api`,
  headers: { 'Content-Type': 'application/json' },
  timeout: 30000,
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

export default api;
