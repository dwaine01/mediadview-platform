// MediaView Dark SaaS Theme
export const COLORS = {
  // Primary brand
  primary: '#6366F1',
  primaryLight: '#818CF8',
  primaryDark: '#4F46E5',
  accent: '#22D3EE',
  accentDark: '#0891B2',

  // Status
  success: '#10B981',
  successBg: 'rgba(16,185,129,0.12)',
  warning: '#F59E0B',
  warningBg: 'rgba(245,158,11,0.12)',
  error: '#EF4444',
  errorBg: 'rgba(239,68,68,0.12)',

  // Dark backgrounds
  bg: '#0B0F1A',
  bgCard: '#111827',
  bgElevated: '#1F2937',
  bgHover: '#1E293B',
  sidebar: '#0F172A',
  sidebarActive: 'rgba(99,102,241,0.15)',
  sidebarBorder: '#1E293B',

  // Text
  text: '#F1F5F9',
  textSecondary: '#94A3B8',
  textMuted: '#64748B',
  textDim: '#475569',

  // Borders
  border: '#1E293B',
  borderLight: '#374151',
  divider: '#1E293B',

  // Legacy compat
  background: '#0B0F1A',
  surface: '#111827',
  surfaceAlt: '#1F2937',
  white: '#FFFFFF',
  black: '#000000',
  overlay: 'rgba(0,0,0,0.6)',
  secondary: '#0EA5E9',
  successLight: '#D1FAE5',
  warningLight: '#FEF3C7',
  errorLight: '#FEE2E2',
  textLight: '#94A3B8',
  borderLight2: '#F1F5F9',
};

export const SHADOWS = {
  small: {
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.3,
    shadowRadius: 3,
    elevation: 2,
  },
  medium: {
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.4,
    shadowRadius: 8,
    elevation: 4,
  },
  large: {
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.5,
    shadowRadius: 16,
    elevation: 8,
  },
};

export const CITY_COLORS: Record<string, string> = {
  'New York': '#3B82F6',
  'Los Angeles': '#F97316',
  'Miami': '#14B8A6',
  'Chicago': '#8B5CF6',
  'Las Vegas': '#EAB308',
  'San Francisco': '#EC4899',
  'Houston': '#22C55E',
  'Dallas': '#6366F1',
  'Seattle': '#06B6D4',
};

export const getStatusStyle = (status: string) => {
  switch (status) {
    case 'active': return { bg: 'rgba(16,185,129,0.15)', text: '#34D399' };
    case 'pending': return { bg: 'rgba(245,158,11,0.15)', text: '#FBBF24' };
    case 'approved': return { bg: 'rgba(59,130,246,0.15)', text: '#60A5FA' };
    case 'rejected': return { bg: 'rgba(239,68,68,0.15)', text: '#F87171' };
    case 'draft': return { bg: 'rgba(100,116,139,0.15)', text: '#94A3B8' };
    case 'completed': return { bg: 'rgba(99,102,241,0.15)', text: '#A5B4FC' };
    default: return { bg: 'rgba(100,116,139,0.15)', text: '#94A3B8' };
  }
};
