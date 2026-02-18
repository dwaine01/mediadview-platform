import axios from 'axios';
import AsyncStorage from '@react-native-async-storage/async-storage';

const API_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';

const api = axios.create({
  baseURL: `${API_URL}/api`,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add auth token to requests
api.interceptors.request.use(async (config) => {
  const token = await AsyncStorage.getItem('auth_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Auth
export const login = async (email: string, password: string) => {
  const response = await api.post('/auth/login', { email, password });
  return response.data;
};

export const registerWorkshop = async (
  workshopName: string,
  adminName: string,
  adminEmail: string,
  adminPassword: string
) => {
  const response = await api.post('/auth/register-workshop', null, {
    params: {
      admin_email: adminEmail,
      admin_password: adminPassword,
      admin_name: adminName,
    },
    data: { name: workshopName },
  });
  return response.data;
};

export const getMe = async () => {
  const response = await api.get('/auth/me');
  return response.data;
};

// VIN
export const decodeVin = async (vin: string) => {
  const response = await api.get(`/vin/decode/${vin}`);
  return response.data;
};

// Clients
export const getClients = async (search?: string) => {
  const response = await api.get('/clients', { params: { search } });
  return response.data;
};

export const createClient = async (data: {
  name: string;
  phone?: string;
  email?: string;
  address?: string;
  notes?: string;
}) => {
  const response = await api.post('/clients', data);
  return response.data;
};

export const getClient = async (id: string) => {
  const response = await api.get(`/clients/${id}`);
  return response.data;
};

export const updateClient = async (id: string, data: {
  name?: string;
  phone?: string;
  email?: string;
  address?: string;
  notes?: string;
  has_credit?: boolean;
  credit_limit?: number;
}) => {
  const response = await api.put(`/clients/${id}`, data);
  return response.data;
};

// Credit Reports
export const getCreditReport = async () => {
  const response = await api.get('/reports/credit');
  return response.data;
};

// Vehicles
export const getVehicles = async (clientId?: string) => {
  const response = await api.get('/vehicles', { params: { client_id: clientId } });
  return response.data;
};

export const getVehicleByVin = async (vin: string) => {
  const response = await api.get(`/vehicles/by-vin/${vin}`);
  return response.data;
};

export const createVehicle = async (data: {
  client_id: string;
  vin: string;
  make?: string;
  model?: string;
  year?: number;
  trim?: string;
  body_type?: string;
  engine?: string;
  color?: string;
}) => {
  const response = await api.post('/vehicles', data);
  return response.data;
};

// Services
export const getServices = async (category?: string) => {
  const response = await api.get('/services', { params: { category } });
  return response.data;
};

export const createService = async (data: {
  code: string;
  name: string;
  category: string;
  default_price: number;
}) => {
  const response = await api.post('/services', data);
  return response.data;
};

// Work Orders
export const getWorkOrders = async (params?: {
  status?: string;
  tech_id?: string;
  date?: string;
}) => {
  const response = await api.get('/work-orders', { params });
  return response.data;
};

export const getWorkOrder = async (id: string) => {
  const response = await api.get(`/work-orders/${id}`);
  return response.data;
};

export const createWorkOrder = async (data: {
  vehicle_id: string;
  client_id: string;
  tech_id?: string;
  services?: Array<{
    service_id: string;
    service_name: string;
    quantity: number;
    price: number;
    side?: string;
    notes?: string;
  }>;
  odometer?: number;
  notes?: string;
}) => {
  const response = await api.post('/work-orders', data);
  return response.data;
};

export const updateWorkOrder = async (id: string, data: {
  status?: string;
  services?: Array<any>;
  odometer?: number;
  notes?: string;
  photos_before?: string[];
  photos_after?: string[];
}) => {
  const response = await api.put(`/work-orders/${id}`, data);
  return response.data;
};

// Payments
export const getPayment = async (workOrderId: string) => {
  const response = await api.get(`/payments/${workOrderId}`);
  return response.data;
};

export const createPayment = async (data: {
  work_order_id: string;
  method: string;
  payment_status?: string;
  subtotal: number;
  tax: number;
  discount?: number;
  total: number;
  paid_amount?: number;
  reference?: string;
  receipt_photo?: string;
}) => {
  const response = await api.post('/payments', data);
  return response.data;
};

export const updatePayment = async (paymentId: string, data: {
  method?: string;
  payment_status?: string;
  paid_amount?: number;
  reference?: string;
  receipt_photo?: string;
}) => {
  const response = await api.put(`/payments/${paymentId}`, data);
  return response.data;
};

// Reports
export const getDailyReport = async (date?: string, techId?: string) => {
  const response = await api.get('/reports/daily', {
    params: { date, tech_id: techId },
  });
  return response.data;
};

// Workshop
export const getWorkshop = async () => {
  const response = await api.get('/workshop');
  return response.data;
};

export const updateWorkshop = async (data: {
  tax_rate?: number;
  name?: string;
  address?: string;
  phone?: string;
}) => {
  const response = await api.put('/workshop', null, { params: data });
  return response.data;
};

// Users
export const getUsers = async () => {
  const response = await api.get('/users');
  return response.data;
};

export const createUser = async (data: {
  name: string;
  email: string;
  password: string;
  role: string;
  workshop_id: string;
}) => {
  const response = await api.post('/users', data);
  return response.data;
};

export default api;
