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
      {/* Navy top bar — same concept as the pricing page */}
      <View style={[s.topbar, { paddingTop: insets.top + 12 }]}>
        <View style={s.topbarInner}>
          <View style={s.brandRow}>
            <View style={s.brandMark}><Text style={s.brandMarkText}>MV</Text></View>
            <Text style={s.topBrandName}>MediaView</Text>
          </View>
          <TouchableOpacity onPress={() => router.push('/(auth)/pricing')} style={s.topLink} activeOpacity={0.75}>
            <Text style={s.topLinkText}>Ver planes</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* Subtle decoration orbs */}
      <View style={s.orb1} />
      <View style={s.orb2} />

      <ScrollView
        testID="login-screen"
        contentContainerStyle={[s.scroll, { paddingTop: SH > 800 ? 56 : 32 }]}
        keyboardShouldPersistTaps="handled"
      >
        {/* Brand */}
        <View style={s.logoArea}>
          <Text style={s.brandName}>Bienvenido de vuelta</Text>
          <Text style={s.brandTag}>Entra a tu panel para administrar tus pantallas</Text>
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

  /* navy top bar */
  topbar: { backgroundColor: '#020C1B', paddingBottom: 12, paddingHorizontal: 20 },
  topbarInner: { flexDirection: 'row', alignItems: 'center', gap: 12, width: '100%', maxWidth: 1240, alignSelf: 'center' },
  brandRow: { flexDirection: 'row', alignItems: 'center', gap: 9, flex: 1 },
  brandMark: { width: 32, height: 32, borderRadius: 9, backgroundColor: '#06B6D4', alignItems: 'center', justifyContent: 'center' },
  brandMarkText: { fontSize: 13, fontWeight: '900', color: '#04212B' },
  topBrandName: { fontSize: 16, fontWeight: '800', color: '#FFFFFF', letterSpacing: -0.3 },
  topLink: { paddingVertical: 10, paddingHorizontal: 14, borderRadius: 10, borderWidth: 1, borderColor: 'rgba(255,255,255,0.18)', minHeight: 40, justifyContent: 'center' },
  topLinkText: { fontSize: 13.5, fontWeight: '600', color: '#E2E8F0' },
  orb1: {
    position: 'absolute', top: -120, right: -100, width: 350, height: 350,
    borderRadius: 175, backgroundColor: 'rgba(6,182,212,0.06)',
  },
  orb2: {
    position: 'absolute', bottom: -80, left: -120, width: 280, height: 280,
    borderRadius: 140, backgroundColor: 'rgba(6,182,212,0.04)',
  },
  scroll: { flexGrow: 1, paddingHorizontal: 28, paddingBottom: 40, alignItems: 'center' },

  logoArea: { alignItems: 'center', marginBottom: 32, maxWidth: 420 },
  brandName: { fontSize: 27, fontWeight: '900', color: '#0F172A', letterSpacing: -0.8, textAlign: 'center' },
  brandTag: { fontSize: 14.5, color: '#475569', marginTop: 8, textAlign: 'center', lineHeight: 21 },

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
