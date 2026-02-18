import React from 'react';
import { View, Text, StyleSheet } from 'react-native';

interface PaymentBadgeProps {
  status: 'pagado' | 'pendiente';
}

const statusColors = {
  pagado: { bg: '#10B981', text: '#FFFFFF' },
  pendiente: { bg: '#EF4444', text: '#FFFFFF' },
};

const statusLabels = {
  pagado: 'Pagado',
  pendiente: 'Pendiente',
};

export const PaymentBadge: React.FC<PaymentBadgeProps> = ({ status }) => {
  const colors = statusColors[status] || statusColors.pendiente;
  
  return (
    <View style={[styles.badge, { backgroundColor: colors.bg }]}>
      <Text style={[styles.text, { color: colors.text }]}>
        {statusLabels[status] || status}
      </Text>
    </View>
  );
};

const styles = StyleSheet.create({
  badge: {
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 12,
  },
  text: {
    fontSize: 12,
    fontWeight: '600',
  },
});
