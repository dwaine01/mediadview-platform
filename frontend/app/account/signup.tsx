import React, { useCallback, useEffect, useState } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, ScrollView, StyleSheet,
  KeyboardAvoidingView, Platform, ActivityIndicator, Dimensions,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { signupAPI, plansAPI } from '../../src/services/api';
import { useAuthStore } from '../../src/store/authStore';
import type { Plan } from '../../src/types';

const { width: SW } = Dimensions.get('window');
const IS_DESKTOP = Platform.OS === 'web' && SW > 768;

const PLAN_COLORS: Record<string, string> = {
  free: '#64748B', starter: '#0E7490', pro: '#06B6D4', enterprise: '#D97706',
};

export default function SignupScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { plan_id: paramPlanId, billing_cycle: paramCycle, screen_count: paramScreens } =
    useLocalSearchParams<{ plan_id?: string; billing_cycle?: string; screen_count?: string }>();
  const { login } = useAuthStore();

  const [selectedPlan] = useState(paramPlanId || 'starter');
  const billingCycle: 'monthly' | 'annual' = paramCycle === 'annual' ? 'annual' : 'monthly';
  const screenCount = Math.max(1, parseInt(paramScreens || '1', 10) || 1);
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

  const planColor = PLAN_COLORS[selectedPlan] || '#06B6D4';

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
        billing_cycle: billingCycle,
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
  }, [businessName, contactName, email, phone, password, selectedPlan, billingCycle, login, router]);

  // ─── Label style helper ───
  const labelStyle = sf.label;
  const inputBoxStyle = (key: string) => [sf.inputBox, focused === key && sf.inputFocused];

  return (
    <KeyboardAvoidingView style={sf.root} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
      {/* Header */}
      <View style={[sf.header, { paddingTop: insets.top + 12 }]}>
        <View style={sf.headerInner}>
          <TouchableOpacity
            onPress={() => router.back()}
            style={sf.backBtn}
            hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
          >
            <Ionicons name="arrow-back" size={20} color="#FFFFFF" />
          </TouchableOpacity>
          <View style={sf.brandRow}>
            <View style={sf.brandMark}><Text style={sf.brandMarkText}>MV</Text></View>
            <Text style={sf.topBrandName}>MediaView</Text>
          </View>
          <TouchableOpacity onPress={() => router.push('/account/login')} style={sf.topLink} activeOpacity={0.75}>
            <Text style={sf.topLinkText}>Iniciar sesión</Text>
          </TouchableOpacity>
        </View>
      </View>

      <ScrollView
        contentContainerStyle={IS_DESKTOP ? sf.scrollDesktop : sf.scrollMobile}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        {/* Centered form wrapper */}
        <View style={IS_DESKTOP ? sf.formWrapperDesktop : sf.formWrapperMobile}>

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
                <Text style={sf.planName}>
                  {planConfig.display_name}{planConfig.trial_days > 0 ? ` · ${planConfig.trial_days} días gratis` : ''}
                </Text>
                <Text style={sf.planSub}>
                  {planConfig.monthly_price === 0
                    ? 'Gratis para siempre'
                    : billingCycle === 'annual'
                      ? `Cobro anual · ${screenCount} pantalla${screenCount !== 1 ? 's' : ''}${(planConfig.annual_free_months ?? 0) > 0 ? ` · ${planConfig.annual_free_months} meses gratis` : ''}`
                      : `$${planConfig.monthly_price}/mes · ${screenCount} pantalla${screenCount !== 1 ? 's' : ''}`}
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

            {/* Business Name — full width */}
            <View style={sf.field}>
              <Text style={labelStyle}>NOMBRE DEL NEGOCIO *</Text>
              <View style={inputBoxStyle('business')}>
                <TextInput
                  style={sf.input}
                  value={businessName}
                  onChangeText={setBusinessName}
                  placeholder="Mi Restaurante"
                  placeholderTextColor="#9CA3AF"
                  autoCapitalize="words"
                  autoCorrect={false}
                  onFocus={() => setFocused('business')}
                  onBlur={() => setFocused('')}
                />
              </View>
            </View>

            {/* Name + Phone — 2 columns on desktop, stacked on mobile */}
            <View style={IS_DESKTOP ? sf.row2 : sf.col1}>
              <View style={[sf.field, IS_DESKTOP && sf.flexHalf]}>
                <Text style={labelStyle}>TU NOMBRE COMPLETO *</Text>
                <View style={inputBoxStyle('name')}>
                  <TextInput
                    style={sf.input}
                    value={contactName}
                    onChangeText={setContactName}
                    placeholder="Juan Pérez"
                    placeholderTextColor="#9CA3AF"
                    autoCapitalize="words"
                    autoCorrect={false}
                    onFocus={() => setFocused('name')}
                    onBlur={() => setFocused('')}
                  />
                </View>
              </View>
              <View style={[sf.field, IS_DESKTOP && sf.flexHalf]}>
                <Text style={labelStyle}>TELÉFONO (OPCIONAL)</Text>
                <View style={inputBoxStyle('phone')}>
                  <TextInput
                    style={sf.input}
                    value={phone}
                    onChangeText={setPhone}
                    placeholder="+1 555 000 0000"
                    placeholderTextColor="#9CA3AF"
                    keyboardType="phone-pad"
                    autoCapitalize="none"
                    autoCorrect={false}
                    onFocus={() => setFocused('phone')}
                    onBlur={() => setFocused('')}
                  />
                </View>
              </View>
            </View>

            {/* Email — full width */}
            <View style={sf.field}>
              <Text style={labelStyle}>CORREO ELECTRÓNICO *</Text>
              <View style={inputBoxStyle('email')}>
                <TextInput
                  style={sf.input}
                  value={email}
                  onChangeText={setEmail}
                  placeholder="juan@minegocio.com"
                  placeholderTextColor="#9CA3AF"
                  keyboardType="email-address"
                  autoCapitalize="none"
                  autoCorrect={false}
                  onFocus={() => setFocused('email')}
                  onBlur={() => setFocused('')}
                />
              </View>
            </View>

            {/* Password — full width */}
            <View style={sf.field}>
              <Text style={labelStyle}>CONTRASEÑA *</Text>
              <View style={inputBoxStyle('pwd')}>
                <TextInput
                  style={sf.input}
                  value={password}
                  onChangeText={setPassword}
                  placeholder="Mínimo 8 caracteres"
                  placeholderTextColor="#9CA3AF"
                  secureTextEntry={!showPwd}
                  autoCapitalize="none"
                  autoCorrect={false}
                  onFocus={() => setFocused('pwd')}
                  onBlur={() => setFocused('')}
                />
                <TouchableOpacity
                  onPress={() => setShowPwd(v => !v)}
                  hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
                >
                  <Ionicons name={showPwd ? 'eye-off' : 'eye'} size={18} color="#9CA3AF" />
                </TouchableOpacity>
              </View>
            </View>

          </View>

          {/* Error */}
          {error !== '' && (
            <View style={sf.errorBox}>
              <Ionicons name="warning" size={16} color="#EF4444" />
              <Text style={sf.errorText}>{error}</Text>
            </View>
          )}

          {/* Submit */}
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
            <TouchableOpacity onPress={() => router.push('/account/login')}>
              <Text style={sf.loginLinkBold}>Iniciar Sesión</Text>
            </TouchableOpacity>
          </View>

          <View style={{ height: insets.bottom + 40 }} />
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const sf = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#FFFFFF' },

  header: { backgroundColor: '#020C1B', paddingHorizontal: 20, paddingBottom: 12 },
  headerInner: { flexDirection: 'row', alignItems: 'center', gap: 12, width: '100%', maxWidth: 1240, alignSelf: 'center' },
  backBtn: { width: 40, height: 40, borderRadius: 10, alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(255,255,255,0.08)' },
  brandRow: { flexDirection: 'row', alignItems: 'center', gap: 9, flex: 1 },
  brandMark: { width: 32, height: 32, borderRadius: 9, backgroundColor: '#06B6D4', alignItems: 'center', justifyContent: 'center' },
  brandMarkText: { fontSize: 13, fontWeight: '900', color: '#04212B' },
  topBrandName: { fontSize: 16, fontWeight: '800', color: '#FFFFFF', letterSpacing: -0.3 },
  topLink: { paddingVertical: 10, paddingHorizontal: 14, borderRadius: 10, borderWidth: 1, borderColor: 'rgba(255,255,255,0.18)', minHeight: 40, justifyContent: 'center' },
  topLinkText: { fontSize: 13.5, fontWeight: '600', color: '#E2E8F0' },

  /* ── Scroll containers ── */
  scrollMobile: { flexGrow: 1 },
  scrollDesktop: { flexGrow: 1, alignItems: 'center', paddingVertical: 40 },

  /* ── Form wrappers ── */
  formWrapperMobile: { padding: 24 },
  formWrapperDesktop: {
    width: '100%', maxWidth: 700,
    paddingHorizontal: 40, paddingVertical: 8,
  },

  /* ── Row / column helpers for 2-col layout ── */
  row2: { flexDirection: 'row', gap: 16 },
  col1: {},
  flexHalf: { flex: 1 },

  /* ── Plan badge ── */
  planBadge: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    backgroundColor: '#F8FAFC', borderWidth: 1, borderRadius: 14,
    padding: 14, marginBottom: 24,
  },
  planIconBox: { width: 36, height: 36, borderRadius: 10, justifyContent: 'center', alignItems: 'center' },
  planName: { fontSize: 14, fontWeight: '700', color: '#0F172A' },
  planSub: { fontSize: 11, color: '#64748B', marginTop: 2 },

  /* ── Copy ── */
  title: { fontSize: 22, fontWeight: '800', color: '#0F172A', marginBottom: 6 },
  subtitle: { fontSize: 13, color: '#475569', marginBottom: 24, lineHeight: 18 },

  /* ── Form ── */
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

  /* ── Error ── */
  errorBox: {
    flexDirection: 'row', alignItems: 'flex-start', gap: 8,
    backgroundColor: '#FEF2F2', borderWidth: 1, borderColor: '#FECACA',
    borderRadius: 10, padding: 12, marginTop: 16,
  },
  errorText: { fontSize: 13, color: '#EF4444', flex: 1, lineHeight: 18 },

  /* ── Submit ── */
  submitBtn: {
    backgroundColor: '#06B6D4', borderRadius: 14, paddingVertical: 16,
    alignItems: 'center', marginTop: 20,
    shadowColor: '#06B6D4', shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.3, shadowRadius: 16, elevation: 8,
  },
  submitText: { fontSize: 16, fontWeight: '700', color: '#FFF', letterSpacing: 0.3 },

  /* ── Footer links ── */
  legalText: { fontSize: 11, color: '#94A3B8', textAlign: 'center', marginTop: 14, lineHeight: 16 },
  loginLink: { flexDirection: 'row', justifyContent: 'center', marginTop: 20 },
  loginLinkText: { fontSize: 14, color: '#64748B' },
  loginLinkBold: { fontSize: 14, color: '#0891B2', fontWeight: '700' },
});
