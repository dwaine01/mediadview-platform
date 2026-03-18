export interface User {
  id: string;
  name: string;
  email: string;
  role: 'admin' | 'customer';
  company_name?: string;
  phone?: string;
  language?: string;
  active?: boolean;
  created_at?: string;
}

export interface ScreenLocation {
  city: string;
  address: string;
  state?: string;
  country: string;
  lat?: number;
  lng?: number;
}

export interface ScreenPricing {
  per_hour: number;
  per_day: number;
  per_slot: number;
  currency: string;
}

export interface ScreenSpecs {
  size: string;
  type: string;
  resolution: string;
  orientation: string;
}

export interface Screen {
  id: string;
  name: string;
  description?: string;
  location: ScreenLocation;
  pricing: ScreenPricing;
  specs: ScreenSpecs;
  preview_image?: string;
  status: string;
  active_campaigns?: number;
  created_at?: string;
}

export interface CampaignSchedule {
  start_date: string;
  end_date: string;
  start_time: string;
  end_time: string;
  slot_duration: number;
  frequency: number;
}

export interface CampaignPricing {
  num_days: number;
  hours_per_day: number;
  total_hours: number;
  per_hour: number;
  subtotal: number;
  tax: number;
  total: number;
  currency: string;
}

export interface Campaign {
  id: string;
  user_id: string;
  screen_id: string;
  name: string;
  status: string;
  schedule: CampaignSchedule;
  media_ids: string[];
  pricing: CampaignPricing;
  payment_id?: string;
  admin_notes?: string;
  screen?: Screen;
  media?: MediaItem[];
  screen_name?: string;
  created_at?: string;
  updated_at?: string;
}

export interface MediaItem {
  id: string;
  filename: string;
  content_type: string;
  size: number;
  type: 'image' | 'video';
  data?: string;
  created_at?: string;
}

export interface Payment {
  id: string;
  campaign_id: string;
  amount: number;
  subtotal: number;
  tax: number;
  currency: string;
  status: string;
  method: string;
  card_last4: string;
  invoice_number: string;
  campaign_name?: string;
  screen_name?: string;
  created_at?: string;
}
