import React, { useState, useCallback } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet, Platform,
  KeyboardAvoidingView, ScrollView, ActivityIndicator,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { teamAPI } from '../../src/services/api';
import { useAuthStore } from '../../src/store/authStore';

/**
 * Forced password change for members created by the business owner
 * with a temporary password.
 */
export default function ChangePasswordScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { user, initialize, logout } = useAuthStore();

  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [repeat, setRepeat] = useState('');
  const [show, setShow] = useState(false);
  const [focused, setFocused] = useState('');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  const submit = useCallback(async () => {
    setError('');
    if (next.length < 8) { setError('La nueva contraseña debe tener al menos 8 caracteres.'); return; }
    if (next !== repeat) { setError('Las contraseñas no coinciden.'); return; }
    setSaving(true);
    try {
      await teamAPI.changeMyPassword(current, next);
      await initialize();
      router.replace('/workspace');
    } catch (e: any) {
      setError(e.response?.data?.detail || 'No se pudo cambiar la contraseña.');
    } finally { setSaving(false); }
  }, [current, next, repeat, initialize, router]);

  const box = (key: string) => [cp.inputBox, focused === key && cp.inputFocused];

  return (
    <KeyboardAvoidingView style={cp.root} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
      <View style={[cp.header, { paddingTop: insets.top + 12 }]}>
        <View style={cp.brandRow}>
          <View style={cp.brandMark}><Text style={cp.brandMarkText}>MV</Text></View>
          <Text style={cp.brandName}>MediaView</Text>
        </View>
        <TouchableOpacity onPress={async () => { await logout(); router.replace('/account/login'); }}>
          <Text style={cp.logout}>Salir</Text>
        </TouchableOpacity>
      </View>

      <ScrollView contentContainerStyle={cp.scroll} keyboardShouldPersistTaps="handled">
        <View style={cp.card}>
          <View style={cp.iconBox}><Ionicons name="key-outline" size={26} color="#0891B2" /></View>
          <Text style={cp.title}>Crea tu contraseña</Text>
          <Text style={cp.sub}>
            {user?.name ? `Hola ${user.name}. ` : ''}Tu cuenta se creó con una contraseña temporal.
            Elige una propia para entrar a tu panel.
          </Text>

          <Text style={cp.label}>CONTRASEÑA TEMPORAL</Text>
          <View style={box('cur')}>
            <TextInput
              style={cp.input}
              value={current}
              onChangeText={setCurrent}
              placeholder="La que te dio tu jefe"
              placeholderTextColor="#9CA3AF"
              secureTextEntry={!show}
              autoCapitalize="none"
              onFocus={() => setFocused('cur')}
              onBlur={() => setFocused('')}
            />
          </View>

          <Text style={cp.label}>NUEVA CONTRASEÑA</Text>
          <View style={box('new')}>
            <TextInput
              style={cp.input}
              value={next}
              onChangeText={setNext}
              placeholder="Mínimo 8 caracteres"
              placeholderTextColor="#9CA3AF"
              secureTextEntry={!show}
              autoCapitalize="none"
              onFocus={() => setFocused('new')}
              onBlur={() => setFocused('')}
            />
            <TouchableOpacity onPress={() => setShow(v => !v)} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
              <Ionicons name={show ? 'eye-off' : 'eye'} size={18} color="#9CA3AF" />
            </TouchableOpacity>
          </View>

          <Text style={cp.label}>REPITE LA NUEVA CONTRASEÑA</Text>
          <View style={box('rep')}>
            <TextInput
              style={cp.input}
              value={repeat}
              onChangeText={setRepeat}
              placeholder="Escríbela otra vez"
              placeholderTextColor="#9CA3AF"
              secureTextEntry={!show}
              autoCapitalize="none"
              onFocus={() => setFocused('rep')}
              onBlur={() => setFocused('')}
              onSubmitEditing={submit}
            />
          </View>

          {!!error && (
            <View style={cp.errorBox}>
              <Ionicons name="warning" size={15} color="#DC2626" />
              <Text style={cp.errorText}>{error}</Text>
            </View>
          )}

          <TouchableOpacity style={[cp.btn, saving && { opacity: 0.7 }]} onPress={submit} disabled={saving} activeOpacity={0.85}>
            {saving ? <ActivityIndicator color="#fff" /> : <Text style={cp.btnText}>Guardar y Entrar</Text>}
          </TouchableOpacity>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const cp = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#F8FAFC' },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    backgroundColor: '#020C1B', paddingHorizontal: 20, paddingBottom: 14,
  },
  brandRow: { flexDirection: 'row', alignItems: 'center', gap: 9 },
  brandMark: { width: 32, height: 32, borderRadius: 9, backgroundColor: '#06B6D4', alignItems: 'center', justifyContent: 'center' },
  brandMarkText: { fontSize: 13, fontWeight: '900', color: '#04212B' },
  brandName: { fontSize: 16, fontWeight: '800', color: '#FFFFFF' },
  logout: { color: '#E2E8F0', fontSize: 13.5, fontWeight: '600' },
  scroll: { padding: 20, alignItems: 'center' },
  card: {
    width: '100%', maxWidth: 460, backgroundColor: '#FFFFFF', borderWidth: 1,
    borderColor: '#E2E8F0', borderRadius: 20, padding: 26, marginTop: 24,
  },
  iconBox: { width: 56, height: 56, borderRadius: 16, backgroundColor: '#ECFEFF', alignItems: 'center', justifyContent: 'center', marginBottom: 14 },
  title: { fontSize: 22, fontWeight: '800', color: '#0F172A', marginBottom: 6 },
  sub: { fontSize: 13.5, color: '#475569', lineHeight: 20, marginBottom: 22 },
  label: { fontSize: 11, fontWeight: '700', color: '#475569', letterSpacing: 1.1, marginBottom: 6 },
  inputBox: {
    flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: '#F8FAFC',
    borderWidth: 1.5, borderColor: '#E2E8F0', borderRadius: 12, paddingHorizontal: 16,
    paddingVertical: Platform.OS === 'ios' ? 14 : 12, marginBottom: 16,
  },
  inputFocused: { borderColor: '#06B6D4', backgroundColor: '#FFFFFF' },
  input: {
    flex: 1, fontSize: 15, color: '#0F172A', fontWeight: '500',
    ...(Platform.OS === 'web' ? ({ outlineStyle: 'none', outlineWidth: 0 } as any) : null),
  },
  errorBox: {
    flexDirection: 'row', alignItems: 'flex-start', gap: 8, backgroundColor: '#FEF2F2',
    borderWidth: 1, borderColor: '#FECACA', borderRadius: 10, padding: 12, marginBottom: 8,
  },
  errorText: { fontSize: 13, color: '#DC2626', flex: 1, lineHeight: 18 },
  btn: { backgroundColor: '#0891B2', borderRadius: 14, paddingVertical: 16, alignItems: 'center', marginTop: 8 },
  btnText: { color: '#FFFFFF', fontSize: 15.5, fontWeight: '700' },
});
