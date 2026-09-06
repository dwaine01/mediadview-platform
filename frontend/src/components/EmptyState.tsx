import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

type Action = { label: string; icon?: keyof typeof Ionicons.glyphMap; onPress: () => void };

type Props = {
  icon: keyof typeof Ionicons.glyphMap;
  title: string;
  text: string;
  primary?: Action;
  secondary?: Action;
};

/** Shared workspace empty state: illustration, copy and clear next steps. */
export default function EmptyState({ icon, title, text, primary, secondary }: Props) {
  return (
    <View style={es.wrap}>
      <View style={es.iconBox}>
        <Ionicons name={icon} size={38} color="#0891B2" />
      </View>
      <Text style={es.title}>{title}</Text>
      <Text style={es.text}>{text}</Text>
      {!!primary && (
        <TouchableOpacity style={es.primary} onPress={primary.onPress} activeOpacity={0.85}>
          {!!primary.icon && <Ionicons name={primary.icon} size={16} color="#FFFFFF" />}
          <Text style={es.primaryText}>{primary.label}</Text>
        </TouchableOpacity>
      )}
      {!!secondary && (
        <TouchableOpacity style={es.secondary} onPress={secondary.onPress} activeOpacity={0.8}>
          {!!secondary.icon && <Ionicons name={secondary.icon} size={15} color="#0891B2" />}
          <Text style={es.secondaryText}>{secondary.label}</Text>
        </TouchableOpacity>
      )}
    </View>
  );
}

const es = StyleSheet.create({
  wrap: {
    alignItems: 'center', paddingVertical: 44, paddingHorizontal: 24, gap: 10,
    backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#E2E8F0', borderRadius: 16,
  },
  iconBox: {
    width: 76, height: 76, borderRadius: 22, backgroundColor: '#ECFEFF',
    justifyContent: 'center', alignItems: 'center', marginBottom: 6,
  },
  title: { fontSize: 17, fontWeight: '800', color: '#0F172A', textAlign: 'center' },
  text: { fontSize: 13.5, color: '#64748B', textAlign: 'center', maxWidth: 340, lineHeight: 20 },
  primary: {
    flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 10,
    backgroundColor: '#0891B2', paddingHorizontal: 20, paddingVertical: 13,
    borderRadius: 12, minHeight: 46,
  },
  primaryText: { color: '#FFFFFF', fontSize: 14, fontWeight: '700' },
  secondary: {
    flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 2,
    paddingHorizontal: 14, paddingVertical: 10, minHeight: 44,
  },
  secondaryText: { color: '#0891B2', fontSize: 13.5, fontWeight: '700' },
});
