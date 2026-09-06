export interface User {
  id: string;
  name: string;
  email: string;
  role: 'admin' | 'customer';
  rbac_role?: string;          // Phase 2C: SELF_SERVICE_OWNER | MEDIAVIEW_ADMIN | etc.
  organization_id?: string;    // Phase 2C: workspace tenant scoping
  company_name?: string;
  phone?: string;
  language?: string;
  active?: boolean;
  created_at?: string;
}

export interface Plan {
  plan_id: string;
  display_name: string;
  monthly_price: number;
  annual_price?: number;
  annual_free_months?: number;
  screens_included: number;
  screens_limit?: number | null;
  price_per_extra_screen: number;
  features: string[];
  trial_days: number;
  is_active: boolean;
  is_public: boolean;
  display_order: number;
  highlight: boolean;
  highlight_text?: string;
}

export interface WorkspaceContext {
  organization: {
    id: string;
    name: string;
    slug: string;
    plan: string;
    status: string;
    created_at?: string;
  };
  subscription?: {
    id: string;
    status: string;
    trial_ends_at?: string;
    current_period_start?: string;
    current_period_end?: string;
  };
  plan_config?: Plan;
  stats: {
    screens: number;
    users: number;
    devices: number;
    devices_online?: number;
    devices_offline?: number;
  };
  current_user: {
    id: string;
    name: string;
    email: string;
    rbac_role: string;
    organization_id: string;
  };
}

export interface WorkspaceScreen {
  id: string;
  name: string;
  status?: string;
  code?: string;
  organization_id?: string;
  location?: { city?: string; state?: string; address?: string };
  created_at?: string;
}

export interface WorkspaceUser {
  id: string;
  name: string;
  email: string;
  rbac_role?: string;
  role?: string;
  created_at?: string;
}

export interface BillingData {
  subscription?: {
    id: string;
    status: string;
    trial_ends_at?: string;
    current_period_start?: string;
    current_period_end?: string;
  };
  current_pricing_agreement?: {
    plan_id: string;
    pricing_model: string;
    agreed_monthly_price: number;
    screens_included: number;
    screens_limit?: number | null;
    billing_cycle: string;
    effective_from?: string;
    notes?: string;
  };
  plan_config?: Plan;
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
