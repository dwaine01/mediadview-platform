export const COLORS = {
  primary: '#4F46E5',
  primaryLight: '#818CF8',
  primaryDark: '#3730A3',
  secondary: '#0EA5E9',
  success: '#10B981',
  successLight: '#D1FAE5',
  warning: '#F59E0B',
  warningLight: '#FEF3C7',
  error: '#EF4444',
  errorLight: '#FEE2E2',
  background: '#F1F5F9',
  surface: '#FFFFFF',
  surfaceAlt: '#F8FAFC',
  text: '#0F172A',
  textSecondary: '#64748B',
  textLight: '#94A3B8',
  border: '#E2E8F0',
  borderLight: '#F1F5F9',
  white: '#FFFFFF',
  black: '#000000',
  overlay: 'rgba(0,0,0,0.5)',
};

export const SHADOWS = {
  small: {
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 2,
    elevation: 1,
  },
  medium: {
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.08,
    shadowRadius: 6,
    elevation: 3,
  },
  large: {
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.12,
    shadowRadius: 12,
    elevation: 5,
  },
};

export const CITY_COLORS: Record<string, string> = {
  'New York': '#1E3A8A',
  'Los Angeles': '#9A3412',
  'Miami': '#0F766E',
  'Chicago': '#6D28D9',
  'Las Vegas': '#A16207',
  'San Francisco': '#BE123C',
  'Houston': '#15803D',
  'Dallas': '#4338CA',
  'Seattle': '#047857',
};

export const getStatusStyle = (status: string) => {
  switch (status) {
    case 'active': return { bg: '#D1FAE5', text: '#065F46' };
    case 'pending': return { bg: '#FEF3C7', text: '#92400E' };
    case 'approved': return { bg: '#DBEAFE', text: '#1E40AF' };
    case 'rejected': return { bg: '#FEE2E2', text: '#991B1B' };
    case 'draft': return { bg: '#F1F5F9', text: '#475569' };
    case 'completed': return { bg: '#E0E7FF', text: '#3730A3' };
    default: return { bg: '#F1F5F9', text: '#475569' };
  }
};
