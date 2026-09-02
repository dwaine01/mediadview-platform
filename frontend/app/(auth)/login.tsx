import React, { useState } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  KeyboardAvoidingView, Platform, ScrollView, ActivityIndicator, Alert,
  Dimensions,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useAuthStore } from '../../src/store/authStore';
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
    if (!email.trim() || !password.trim()) { Alert.alert('Error', 'Please fill in all fields'); return; }
    try { await login(email.trim(), password); router.replace('/(tabs)'); }
    catch (e: any) { Alert.alert('Login Failed', e.message); }
  };

  return (
    <KeyboardAvoidingView style={s.root} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
      {/* Decorative orbs */}
      <View style={s.orb1} />
      <View style={s.orb2} />

      <ScrollView testID="login-screen" contentContainerStyle={[s.scroll, { paddingTop: insets.top + (SH > 800 ? 80 : 40) }]} keyboardShouldPersistTaps="handled">
        {/* Logo */}
        <View style={s.logoArea}>
          <View style={s.logoOuter}>
            <View style={s.logoInner}>
              <Text style={s.logoLetters}>MV</Text>
            </View>
          </View>
          <Text style={s.brandName}>MediaView</Text>
          <Text style={s.brandTag}>Digital Signage Platform</Text>
        </View>

        {/* Card */}
        <View style={s.card}>
          <Text style={s.cardTitle}>Sign in to your account</Text>

          <View style={s.field}>
            <Text style={s.label}>EMAIL</Text>
            <View style={[s.inputBox, focused === 'email' && s.inputFocused]}>
              <Ionicons name="mail" size={18} color={focused === 'email' ? '#818CF8' : '#475569'} />
              <TextInput testID="login-email-input" style={s.input} placeholder="you@company.com" placeholderTextColor="#374151"
                value={email} onChangeText={setEmail} keyboardType="email-address" autoCapitalize="none"
                onFocus={() => setFocused('email')} onBlur={() => setFocused('')} />
            </View>
          </View>

          <View style={s.field}>
            <Text style={s.label}>PASSWORD</Text>
            <View style={[s.inputBox, focused === 'pwd' && s.inputFocused]}>
              <Ionicons name="lock-closed" size={18} color={focused === 'pwd' ? '#818CF8' : '#475569'} />
              <TextInput testID="login-password-input" style={s.input} placeholder="Enter password" placeholderTextColor="#374151"
                value={password} onChangeText={setPassword} secureTextEntry={!showPwd}
                onFocus={() => setFocused('pwd')} onBlur={() => setFocused('')} />
              <TouchableOpacity testID="login-password-visibility-button" onPress={() => setShowPwd(!showPwd)} hitSlop={{top:10,bottom:10,left:10,right:10}}>
                <Ionicons name={showPwd ? 'eye-off' : 'eye'} size={18} color="#475569" />
              </TouchableOpacity>
            </View>
          </View>

          <TouchableOpacity testID="login-submit-button" style={[s.btn, isLoading && { opacity: 0.7 }]} onPress={handleLogin} disabled={isLoading} activeOpacity={0.8}>
            <View style={s.btnGrad} />
            {isLoading ? <ActivityIndicator color="#FFF" /> : <Text style={s.btnText}>Sign In</Text>}
          </TouchableOpacity>
        </View>

        <TouchableOpacity testID="login-register-button" style={s.linkRow} onPress={() => router.push('/(auth)/register')}>
          <Text style={s.linkText}>Need an account?</Text>
          <Text style={s.linkBold}> Create one</Text>
        </TouchableOpacity>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#050816' },
  // Decorative gradient orbs
  orb1: { position: 'absolute', top: -100, right: -80, width: 300, height: 300, borderRadius: 150, backgroundColor: 'rgba(99,102,241,0.08)' },
  orb2: { position: 'absolute', bottom: -50, left: -100, width: 250, height: 250, borderRadius: 125, backgroundColor: 'rgba(34,211,238,0.05)' },

  scroll: { flexGrow: 1, paddingHorizontal: 28, paddingBottom: 40, alignItems: 'center' },

  // Logo
  logoArea: { alignItems: 'center', marginBottom: 44 },
  logoOuter: {
    width: 80, height: 80, borderRadius: 22, backgroundColor: 'rgba(99,102,241,0.15)',
    justifyContent: 'center', alignItems: 'center', marginBottom: 18,
    borderWidth: 1, borderColor: 'rgba(99,102,241,0.3)',
  },
  logoInner: {
    width: 60, height: 60, borderRadius: 16, backgroundColor: '#6366F1',
    justifyContent: 'center', alignItems: 'center',
    shadowColor: '#6366F1', shadowOffset: { width: 0, height: 8 }, shadowOpacity: 0.5, shadowRadius: 20, elevation: 10,
  },
  logoLetters: { fontSize: 22, fontWeight: '900', color: '#FFF', letterSpacing: 1 },
  brandName: { fontSize: 30, fontWeight: '800', color: '#F1F5F9', letterSpacing: -0.5 },
  brandTag: { fontSize: 14, color: '#6366F1', fontWeight: '500', marginTop: 4, letterSpacing: 0.5 },

  // Card
  card: {
    width: '100%', maxWidth: 420, backgroundColor: '#0D1225',
    borderRadius: 24, padding: 32, borderWidth: 1, borderColor: '#1E293B',
  },
  cardTitle: { fontSize: 20, fontWeight: '700', color: '#E2E8F0', marginBottom: 28, textAlign: 'center' },

  // Fields
  field: { marginBottom: 20 },
  label: { fontSize: 11, fontWeight: '700', color: '#64748B', letterSpacing: 1.5, marginBottom: 8 },
  inputBox: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    backgroundColor: '#0F172A', borderWidth: 1.5, borderColor: '#1E293B',
    borderRadius: 14, paddingHorizontal: 16, paddingVertical: Platform.OS === 'ios' ? 16 : 12,
  },
  inputFocused: { borderColor: '#6366F1', backgroundColor: '#0C1322' },
  input: { flex: 1, fontSize: 16, color: '#F1F5F9', fontWeight: '500' },

  // Button
  btn: {
    marginTop: 8, borderRadius: 14, overflow: 'hidden',
    backgroundColor: '#6366F1', paddingVertical: 16, alignItems: 'center',
    shadowColor: '#6366F1', shadowOffset: { width: 0, height: 6 }, shadowOpacity: 0.4, shadowRadius: 16, elevation: 8,
  },
  btnGrad: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: '#4F46E5', opacity: 0.5, borderRadius: 14,
  },
  btnText: { fontSize: 16, fontWeight: '700', color: '#FFF', letterSpacing: 0.5 },

  // Link
  linkRow: { flexDirection: 'row', marginTop: 28 },
  linkText: { fontSize: 14, color: '#475569' },
  linkBold: { fontSize: 14, color: '#818CF8', fontWeight: '700' },
});
