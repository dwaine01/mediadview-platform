import React from 'react';
import { View, Text, StyleSheet } from 'react-native';

interface StatusBadgeProps {
  status: 'asignado' | 'iniciado' | 'pendiente' | 'terminado';
}

const statusColors = {
  asignado: { bg: '#8B5CF6', text: '#FFFFFF' },
  iniciado: { bg: '#3B82F6', text: '#FFFFFF' },
  pendiente: { bg: '#F59E0B', text: '#000000' },
  terminado: { bg: '#10B981', text: '#FFFFFF' },
};

const statusLabels = {
  asignado: 'Asignado',
  iniciado: 'Iniciado',
  pendiente: 'Pendiente',
  terminado: 'Terminado',
};

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status }) => {
  const colors = statusColors[status] || statusColors.iniciado;
  
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
