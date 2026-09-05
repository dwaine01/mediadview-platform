import React, { useCallback, useEffect, useState } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, ScrollView, StyleSheet,
  KeyboardAvoidingView, Platform, ActivityIndicator, Alert, Dimensions,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { signupAPI, plansAPI } from '../../src/services/api';
import { useAuthStore } from '../../src/store/authStore';
import type { Plan } from '../../src/types';

const PLAN_COLORS: Record<string, string> = {
  free: '#64748B', starter: '#6366F1', pro: '#06B6D4', enterprise: '#F59E0B',
};

export default function SignupScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { plan_id: paramPlanId } = useLocalSearchParams<{ plan_id?: string }>();
  const { login } = useAuthStore();

  const [selectedPlan, setSelectedPlan] = useState(paramPlanId || 'starter');
  const [planConfig, setPlanConfig] = useState<Plan | null>(null);
  const [loadingPlan, setLoadingPlan] = useState(true);

  const [businessName, setBusinessName] = useState('');
  const [contactName, setContactName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [password, setPassword] = useState('');
  const [showPwd, setShowPwd] = useState(false);
  const [focused, setFocused] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    (async () => {
      try {
        const res = await plansAPI.listPublic();
        const p = res.data.find((pl: Plan) => pl.plan_id === selectedPlan);
        setPlanConfig(p || null);
      } finally {
        setLoadingPlan(false);
      }
    })();
  }, [selectedPlan]);

  const planColor = PLAN_COLORS[selectedPlan] || '#06B6D4';

  const handleSignup = useCallback(async () => {
    setError('');
    if (!businessName.trim()) { setError('Por favor ingresa el nombre de tu negocio.'); return; }
    if (!contactName.trim()) { setError('Por favor ingresa tu nombre completo.'); return; }
    if (!email.trim() || !email.includes('@')) { setError('Por favor ingresa un correo electrónico válido.'); return; }
    if (!password || password.length < 8) { setError('La contraseña debe tener al menos 8 caracteres.'); return; }

    setSubmitting(true);
    try {
      await signupAPI.customerSignup({
        plan_id: selectedPlan,
        business_name: businessName.trim(),
        contact_name: contactName.trim(),
        contact_email: email.trim().toLowerCase(),
        contact_phone: phone.trim() || null,
        password,
      });
      await login(email.trim().toLowerCase(), password);
      router.replace('/');
    } catch (e: any) {
      const msg = e.response?.data?.detail || e.message || 'Error al crear cuenta. Intenta de nuevo.';
      setError(msg);
      setSubmitting(false);
    }
  }, [businessName, contactName, email, phone, password, selectedPlan, login, router]);

  const Field = ({ label, value, onChangeText, keyboardType, secureTextEntry, rightIcon, onRightIcon, fieldKey, placeholder, autoCapitalize }: any) => (
    <View style={sf.field}>
      <Text style={sf.label}>{label}</Text>
      <View style={[sf.inputBox, focused === fieldKey && sf.inputFocused]}>
        <TextInput
          style={sf.input}
          value={value}
          onChangeText={onChangeText}
          placeholder={placeholder || ''}
          placeholderTextColor="#9CA3AF"
          keyboardType={keyboardType || 'default'}
          secureTextEntry={secureTextEntry}
          autoCapitalize={autoCapitalize || 'sentences'}
          autoCorrect={false}
          onFocus={() => setFocused(fieldKey)}
          onBlur={() => setFocused('')}
        />
        {rightIcon && (
          <TouchableOpacity onPress={onRightIcon} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
            <Ionicons name={rightIcon} size={18} color="#9CA3AF" />
          </TouchableOpacity>
        )}
      </View>
    </View>
  );

  return (
    <KeyboardAvoidingView style={sf.root} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
      <View style={[sf.header, { paddingTop: insets.top + 8 }]}>
        <TouchableOpacity onPress={() => router.back()} style={{ padding: 8 }}>
          <Ionicons name="arrow-back" size={22} color="#64748B" />
        </TouchableOpacity>
        <Text style={sf.headerTitle}>Crear Cuenta</Text>
        <View style={{ width: 38 }} />
      </View>

      <ScrollView contentContainerStyle={sf.scroll} keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
        {/* Plan badge */}
        {!loadingPlan && planConfig && (
          <View style={[sf.planBadge, { borderColor: planColor + '30' }]}>
            <View style={[sf.planIconBox, { backgroundColor: planColor + '15' }]}>
              <Ionicons
                name={selectedPlan === 'free' ? 'gift' : selectedPlan === 'starter' ? 'rocket' : selectedPlan === 'pro' ? 'flash' : 'shield-checkmark'}
                size={18}
                color={planColor}
              />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={sf.planName}>{planConfig.display_name}{planConfig.trial_days > 0 ? ` · ${planConfig.trial_days} días gratis` : ''}</Text>
              <Text style={sf.planSub}>
                {planConfig.monthly_price === 0 ? 'Gratis para siempre' : `$${planConfig.monthly_price}/mes después del período de prueba`}
              </Text>
            </View>
            <TouchableOpacity onPress={() => router.back()} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
              <Text style={{ fontSize: 12, color: '#06B6D4', fontWeight: '600' }}>Cambiar</Text>
            </TouchableOpacity>
          </View>
        )}

        <Text style={sf.title}>Crea tu cuenta</Text>
        <Text style={sf.subtitle}>Completa tus datos. No se requiere tarjeta de crédito.</Text>

        <View style={sf.form}>
          <Field label="NOMBRE DEL NEGOCIO *" value={businessName} onChangeText={setBusinessName}
            placeholder="Mi Restaurante" fieldKey="business" />
          <Field label="TU NOMBRE COMPLETO *" value={contactName} onChangeText={setContactName}
            placeholder="Juan Pérez" fieldKey="name" />
          <Field label="CORREO ELECTRÓNICO *" value={email} onChangeText={setEmail}
            placeholder="juan@minegocio.com" keyboardType="email-address" autoCapitalize="none" fieldKey="email" />
          <Field label="TELÉFONO (OPCIONAL)" value={phone} onChangeText={setPhone}
            placeholder="+1 555 000 0000" keyboardType="phone-pad" autoCapitalize="none" fieldKey="phone" />
          <Field label="CONTRASEÑA *" value={password} onChangeText={setPassword}
            placeholder="Mínimo 8 caracteres" secureTextEntry={!showPwd}
            rightIcon={showPwd ? 'eye-off' : 'eye'} onRightIcon={() => setShowPwd(!showPwd)}
            autoCapitalize="none" fieldKey="pwd" />
        </View>

        {error !== '' && (
          <View style={sf.errorBox}>
            <Ionicons name="warning" size={16} color="#EF4444" />
            <Text style={sf.errorText}>{error}</Text>
          </View>
        )}

        <TouchableOpacity
          style={[sf.submitBtn, submitting && { opacity: 0.7 }]}
          onPress={handleSignup}
          disabled={submitting}
          activeOpacity={0.8}
        >
          {submitting
            ? <ActivityIndicator color="#FFF" />
            : <Text style={sf.submitText}>Crear Cuenta y Comenzar Prueba</Text>}
        </TouchableOpacity>

        <Text style={sf.legalText}>
          Al crear una cuenta aceptas nuestros Términos de Servicio y Política de Privacidad.
        </Text>

        <View style={sf.loginLink}>
          <Text style={sf.loginLinkText}>¿Ya tienes cuenta? </Text>
          <TouchableOpacity onPress={() => router.push('/(auth)/login')}>
            <Text style={sf.loginLinkBold}>Iniciar Sesión</Text>
          </TouchableOpacity>
        </View>

        <View style={{ height: insets.bottom + 40 }} />
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const sf = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#FFFFFF' },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 20, paddingBottom: 12,
    backgroundColor: '#FFFFFF',
    borderBottomWidth: 1, borderBottomColor: '#E2E8F0',
  },
  headerTitle: { fontSize: 17, fontWeight: '700', color: '#0F172A' },
  scroll: { padding: 24 },
  planBadge: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    backgroundColor: '#F8FAFC', borderWidth: 1, borderRadius: 14,
    padding: 14, marginBottom: 24,
  },
  planIconBox: { width: 36, height: 36, borderRadius: 10, justifyContent: 'center', alignItems: 'center' },
  planName: { fontSize: 14, fontWeight: '700', color: '#0F172A' },
  planSub: { fontSize: 11, color: '#64748B', marginTop: 2 },
  title: { fontSize: 22, fontWeight: '800', color: '#0F172A', marginBottom: 6 },
  subtitle: { fontSize: 13, color: '#475569', marginBottom: 24, lineHeight: 18 },
  form: { gap: 14 },
  field: { gap: 6 },
  label: { fontSize: 11, fontWeight: '700', color: '#475569', letterSpacing: 1.2 },
  inputBox: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    backgroundColor: '#F8FAFC', borderWidth: 1.5, borderColor: '#E2E8F0',
    borderRadius: 12, paddingHorizontal: 16,
    paddingVertical: Platform.OS === 'ios' ? 14 : 12,
  },
  inputFocused: { borderColor: '#06B6D4', backgroundColor: '#FFFFFF' },
  input: { flex: 1, fontSize: 15, color: '#0F172A', fontWeight: '500' },
  errorBox: {
    flexDirection: 'row', alignItems: 'flex-start', gap: 8,
    backgroundColor: '#FEF2F2', borderWidth: 1, borderColor: '#FECACA',
    borderRadius: 10, padding: 12, marginTop: 16,
  },
  errorText: { fontSize: 13, color: '#EF4444', flex: 1, lineHeight: 18 },
  submitBtn: {
    backgroundColor: '#06B6D4', borderRadius: 14, paddingVertical: 16,
    alignItems: 'center', marginTop: 20,
    shadowColor: '#06B6D4', shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.3, shadowRadius: 16, elevation: 8,
  },
  submitText: { fontSize: 16, fontWeight: '700', color: '#FFF', letterSpacing: 0.3 },
  legalText: { fontSize: 11, color: '#94A3B8', textAlign: 'center', marginTop: 14, lineHeight: 16 },
  loginLink: { flexDirection: 'row', justifyContent: 'center', marginTop: 20 },
  loginLinkText: { fontSize: 14, color: '#64748B' },
  loginLinkBold: { fontSize: 14, color: '#0891B2', fontWeight: '700' },
});
