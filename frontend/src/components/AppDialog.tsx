import React from 'react';
import { View, Text, Modal, TouchableOpacity, StyleSheet, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

export type DialogOption = {
  label: string;
  onPress?: () => void;
  destructive?: boolean;
  primary?: boolean;
};

export type DialogState = {
  title: string;
  message?: string;
  icon?: keyof typeof Ionicons.glyphMap;
  options?: DialogOption[];
} | null;

type Props = { state: DialogState; onDismiss: () => void };

/**
 * Cross-platform dialog. `Alert.alert` is a no-op on React Native Web,
 * so every confirmation in the workspace goes through this component.
 */
export default function AppDialog({ state, onDismiss }: Props) {
  const { width } = useWindowDimensions();
  if (!state) return null;
  const options = state.options?.length ? state.options : [{ label: 'Entendido', primary: true }];

  return (
    <Modal visible transparent animationType="fade" onRequestClose={onDismiss}>
      <View style={ad.overlay}>
        <View style={[ad.card, { width: Math.min(width - 40, 420) }]}>
          {!!state.icon && (
            <View style={ad.iconBox}><Ionicons name={state.icon} size={24} color="#0891B2" /></View>
          )}
          <Text style={ad.title}>{state.title}</Text>
          {!!state.message && <Text style={ad.message}>{state.message}</Text>}
          <View style={ad.actions}>
            {options.map((o, i) => (
              <TouchableOpacity
                key={`${o.label}-${i}`}
                style={[ad.btn, o.primary && ad.btnPrimary, o.destructive && ad.btnDestructive]}
                onPress={() => { onDismiss(); o.onPress?.(); }}
                activeOpacity={0.85}
              >
                <Text style={[
                  ad.btnText,
                  o.primary && ad.btnTextPrimary,
                  o.destructive && ad.btnTextDestructive,
                ]}>{o.label}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>
      </View>
    </Modal>
  );
}

const ad = StyleSheet.create({
  overlay: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: 'rgba(15,23,42,0.45)', padding: 20 },
  card: { backgroundColor: '#FFFFFF', borderRadius: 18, padding: 24 },
  iconBox: { width: 48, height: 48, borderRadius: 14, backgroundColor: '#ECFEFF', alignItems: 'center', justifyContent: 'center', marginBottom: 12 },
  title: { fontSize: 17, fontWeight: '800', color: '#0F172A' },
  message: { fontSize: 13.5, color: '#475569', lineHeight: 20, marginTop: 8 },
  actions: { gap: 8, marginTop: 20 },
  btn: {
    minHeight: 46, borderRadius: 12, alignItems: 'center', justifyContent: 'center',
    backgroundColor: '#F1F5F9', paddingHorizontal: 16,
  },
  btnPrimary: { backgroundColor: '#0891B2' },
  btnDestructive: { backgroundColor: '#FEF2F2', borderWidth: 1, borderColor: '#FECACA' },
  btnText: { fontSize: 14.5, fontWeight: '700', color: '#334155' },
  btnTextPrimary: { color: '#FFFFFF' },
  btnTextDestructive: { color: '#DC2626' },
});
