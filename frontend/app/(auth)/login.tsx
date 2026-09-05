import React, { useState } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  KeyboardAvoidingView, Platform, ScrollView, ActivityIndicator, Alert,
  Dimensions,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useAuthStore, isWorkspaceUser } from '../../src/store/authStore';
import { Ionicons } from '@expo/vector-icons';

const { height: SH } = Dimensions.get('window');

export default function LoginScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { login, isLoading } = useAuthStore();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPwd, setShowPwd] = useState(false);
  const [focused, setFocused] = useState('');

  const handleLogin = async () => {
    if (!email.trim() || !password.trim()) { Alert.alert('Error', 'Por favor completa todos los campos'); return; }
    try {
      await login(email.trim(), password);
      const updatedUser = useAuthStore.getState().user;
      if (isWorkspaceUser(updatedUser)) {
        router.replace('/workspace');
      } else {
        router.replace('/(tabs)');
      }
    }
    catch (e: any) { Alert.alert('Error al iniciar sesión', e.message); }
  };

  return (
    <KeyboardAvoidingView style={s.root} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
      {/* Subtle decoration orbs */}
      <View style={s.orb1} />
      <View style={s.orb2} />

      <ScrollView
        testID="login-screen"
        contentContainerStyle={[s.scroll, { paddingTop: insets.top + (SH > 800 ? 72 : 36) }]}
        keyboardShouldPersistTaps="handled"
      >
        {/* Brand */}
        <View style={s.logoArea}>
          <View style={s.logoOuter}>
            <View style={s.logoInner}>
              <Text style={s.logoLetters}>MV</Text>
            </View>
          </View>
          <Text style={s.brandName}>MediaView</Text>
          <Text style={s.brandTag}>Digital Signage Platform</Text>
        </View>

        {/* Form card */}
        <View style={s.card}>
          <Text style={s.cardTitle}>Inicia sesión</Text>

          <View style={s.field}>
            <Text style={s.label}>CORREO ELECTRÓNICO</Text>
            <View style={[s.inputBox, focused === 'email' && s.inputFocused]}>
              <Ionicons name="mail" size={18} color={focused === 'email' ? '#06B6D4' : '#9CA3AF'} />
              <TextInput
                testID="login-email-input"
                style={s.input}
                placeholder="tu@empresa.com"
                placeholderTextColor="#9CA3AF"
                value={email}
                onChangeText={setEmail}
                keyboardType="email-address"
                autoCapitalize="none"
                onFocus={() => setFocused('email')}
                onBlur={() => setFocused('')}
              />
            </View>
          </View>

          <View style={s.field}>
            <Text style={s.label}>CONTRASEÑA</Text>
            <View style={[s.inputBox, focused === 'pwd' && s.inputFocused]}>
              <Ionicons name="lock-closed" size={18} color={focused === 'pwd' ? '#06B6D4' : '#9CA3AF'} />
              <TextInput
                testID="login-password-input"
                style={s.input}
                placeholder="Tu contraseña"
                placeholderTextColor="#9CA3AF"
                value={password}
                onChangeText={setPassword}
                secureTextEntry={!showPwd}
                onFocus={() => setFocused('pwd')}
                onBlur={() => setFocused('')}
              />
              <TouchableOpacity
                testID="login-password-visibility-button"
                onPress={() => setShowPwd(!showPwd)}
                hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
              >
                <Ionicons name={showPwd ? 'eye-off' : 'eye'} size={18} color="#9CA3AF" />
              </TouchableOpacity>
            </View>
          </View>

          <TouchableOpacity
            testID="login-submit-button"
            style={[s.btn, isLoading && { opacity: 0.7 }]}
            onPress={handleLogin}
            disabled={isLoading}
            activeOpacity={0.8}
          >
            {isLoading
              ? <ActivityIndicator color="#FFF" />
              : <Text style={s.btnText}>Iniciar Sesión</Text>
            }
          </TouchableOpacity>
        </View>

        <TouchableOpacity
          testID="login-register-button"
          style={s.linkRow}
          onPress={() => router.push('/(auth)/register')}
        >
          <Text style={s.linkText}>¿No tienes cuenta?</Text>
          <Text style={s.linkBold}> Créala aquí</Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={[s.linkRow, { marginTop: 12, justifyContent: 'center' }]}
          onPress={() => router.push('/(auth)/pricing')}
        >
          <Text style={s.linkText}>Ver planes & </Text>
          <Text style={[s.linkBold, { color: '#06B6D4' }]}>Prueba gratis →</Text>
        </TouchableOpacity>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#FFFFFF' },
  orb1: {
    position: 'absolute', top: -120, right: -100, width: 350, height: 350,
    borderRadius: 175, backgroundColor: 'rgba(6,182,212,0.06)',
  },
  orb2: {
    position: 'absolute', bottom: -80, left: -120, width: 280, height: 280,
    borderRadius: 140, backgroundColor: 'rgba(6,182,212,0.04)',
  },
  scroll: { flexGrow: 1, paddingHorizontal: 28, paddingBottom: 40, alignItems: 'center' },

  logoArea: { alignItems: 'center', marginBottom: 40 },
  logoOuter: {
    width: 80, height: 80, borderRadius: 22,
    backgroundColor: 'rgba(6,182,212,0.08)',
    justifyContent: 'center', alignItems: 'center', marginBottom: 16,
    borderWidth: 1, borderColor: 'rgba(6,182,212,0.2)',
  },
  logoInner: {
    width: 60, height: 60, borderRadius: 16, backgroundColor: '#06B6D4',
    justifyContent: 'center', alignItems: 'center',
    shadowColor: '#06B6D4', shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.35, shadowRadius: 20, elevation: 10,
  },
  logoLetters: { fontSize: 22, fontWeight: '900', color: '#FFF', letterSpacing: 1 },
  brandName: { fontSize: 28, fontWeight: '800', color: '#0F172A', letterSpacing: -0.5 },
  brandTag: { fontSize: 14, color: '#0891B2', fontWeight: '500', marginTop: 4 },

  card: {
    width: '100%', maxWidth: 420,
    backgroundColor: '#FFFFFF',
    borderRadius: 24, padding: 32,
    borderWidth: 1, borderColor: '#E2E8F0',
    shadowColor: '#000', shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.07, shadowRadius: 24, elevation: 4,
  },
  cardTitle: { fontSize: 20, fontWeight: '700', color: '#0F172A', marginBottom: 28, textAlign: 'center' },

  field: { marginBottom: 20 },
  label: { fontSize: 11, fontWeight: '700', color: '#64748B', letterSpacing: 1.5, marginBottom: 8 },
  inputBox: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    backgroundColor: '#F8FAFC', borderWidth: 1.5, borderColor: '#E2E8F0',
    borderRadius: 14, paddingHorizontal: 16,
    paddingVertical: Platform.OS === 'ios' ? 16 : 12,
  },
  inputFocused: { borderColor: '#06B6D4', backgroundColor: '#FFFFFF' },
  input: { flex: 1, fontSize: 16, color: '#0F172A', fontWeight: '500' },

  btn: {
    marginTop: 8, borderRadius: 14,
    backgroundColor: '#06B6D4', paddingVertical: 16, alignItems: 'center',
    shadowColor: '#06B6D4', shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.3, shadowRadius: 16, elevation: 8,
  },
  btnText: { fontSize: 16, fontWeight: '700', color: '#FFF', letterSpacing: 0.5 },

  linkRow: { flexDirection: 'row', marginTop: 28 },
  linkText: { fontSize: 14, color: '#64748B' },
  linkBold: { fontSize: 14, color: '#0891B2', fontWeight: '700' },
});
