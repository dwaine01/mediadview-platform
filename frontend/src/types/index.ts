export interface User {
  id: string;
  name: string;
  email: string;
  role: 'admin' | 'tech';
  workshop_id: string;
}

export interface Workshop {
  id: string;
  name: string;
  address?: string;
  phone?: string;
  tax_rate: number;
}

export interface Client {
  id: string;
  workshop_id: string;
  name: string;
  phone?: string;
  email?: string;
  address?: string;
  notes?: string;
  created_at: string;
}

export interface Vehicle {
  id: string;
  workshop_id: string;
  client_id: string;
  vin: string;
  make?: string;
  model?: string;
  year?: number;
  trim?: string;
  body_type?: string;
  engine?: string;
  color?: string;
  created_at: string;
}

export interface VinDecodeResult {
  vin: string;
  make: string;
  model: string;
  year?: number;
  trim?: string;
  body_type?: string;
  engine?: string;
  vehicle_type?: string;
  plant_country?: string;
}

export interface ServiceItem {
  id: string;
  workshop_id: string;
  code: string;
  name: string;
  category: 'srs' | 'cinturones' | 'adas';
  default_price: number;
  active: boolean;
}

export interface WorkOrderService {
  service_id: string;
  service_name: string;
  quantity: number;
  price: number;
  side?: 'left' | 'right' | 'both';
  notes?: string;
}

export interface WorkOrder {
  id: string;
  workshop_id: string;
  vehicle_id: string;
  client_id: string;
  tech_id: string;
  status: 'iniciado' | 'pendiente' | 'terminado';
  services: WorkOrderService[];
  odometer?: number;
  notes?: string;
  photos_before: string[];
  photos_after: string[];
  created_at: string;
  started_at?: string;
  completed_at?: string;
  vehicle?: Vehicle;
  client?: Client;
  tech_name?: string;
  payment?: Payment;
}

export interface Payment {
  id: string;
  workshop_id: string;
  work_order_id: string;
  method: 'zelle' | 'cash' | 'check' | 'other';
  payment_status: 'pagado' | 'pendiente';
  subtotal: number;
  tax: number;
  discount: number;
  total: number;
  paid_amount: number;
  reference?: string;
  receipt_photo?: string;
  created_at: string;
  updated_at: string;
}

export interface DailyReport {
  date: string;
  total_orders: number;
  total_billed: number;
  total_paid: number;
  total_pending: number;
  by_status: {
    iniciado: number;
    pendiente: number;
    terminado: number;
  };
  by_tech: Array<{
    name: string;
    orders: number;
    billed: number;
    paid: number;
  }>;
}
