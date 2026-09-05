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
  free: '#6B7280', starter: '#6366F1', pro: '#22D3EE', enterprise: '#F59E0B',
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

  // Load selected plan info
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

  const planColor = PLAN_COLORS[selectedPlan] || '#6366F1';

  const handleSignup = useCallback(async () => {
    setError('');
    if (!businessName.trim()) { setError('Please enter your business name.'); return; }
    if (!contactName.trim()) { setError('Please enter your full name.'); return; }
    if (!email.trim() || !email.includes('@')) { setError('Please enter a valid email address.'); return; }
    if (!password || password.length < 8) { setError('Password must be at least 8 characters.'); return; }

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
      // Auto-login
      await login(email.trim().toLowerCase(), password);
      // Route to workspace (index.tsx will handle redirect)
      router.replace('/');
    } catch (e: any) {
      const msg = e.response?.data?.detail || e.message || 'Signup failed. Please try again.';
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
          placeholderTextColor="#374151"
          keyboardType={keyboardType || 'default'}
          secureTextEntry={secureTextEntry}
          autoCapitalize={autoCapitalize || 'sentences'}
          autoCorrect={false}
          onFocus={() => setFocused(fieldKey)}
          onBlur={() => setFocused('')}
        />
        {rightIcon && (
          <TouchableOpacity onPress={onRightIcon} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
            <Ionicons name={rightIcon} size={18} color="#475569" />
          </TouchableOpacity>
        )}
      </View>
    </View>
  );

  return (
    <KeyboardAvoidingView style={sf.root} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
      <View style={[sf.header, { paddingTop: insets.top + 8 }]}>
        <TouchableOpacity onPress={() => router.back()} style={{ padding: 8 }}>
          <Ionicons name="arrow-back" size={22} color="#94A3B8" />
        </TouchableOpacity>
        <Text style={sf.headerTitle}>Create Account</Text>
        <View style={{ width: 38 }} />
      </View>

      <ScrollView contentContainerStyle={sf.scroll} keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
        {/* Plan Badge */}
        {!loadingPlan && planConfig && (
          <View style={[sf.planBadge, { borderColor: planColor + '44' }]}>
            <View style={[sf.planIconBox, { backgroundColor: planColor + '22' }]}>
              <Ionicons
                name={selectedPlan === 'free' ? 'gift' : selectedPlan === 'starter' ? 'rocket' : selectedPlan === 'pro' ? 'flash' : 'shield-checkmark'}
                size={18}
                color={planColor}
              />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={sf.planName}>{planConfig.display_name} Plan{planConfig.trial_days > 0 ? ` · ${planConfig.trial_days}-day free trial` : ''}</Text>
              <Text style={sf.planSub}>
                {planConfig.monthly_price === 0 ? 'Free forever' : `$${planConfig.monthly_price}/month after trial`}
              </Text>
            </View>
            <TouchableOpacity onPress={() => router.back()} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
              <Text style={{ fontSize: 12, color: '#6366F1', fontWeight: '600' }}>Change</Text>
            </TouchableOpacity>
          </View>
        )}

        <Text style={sf.title}>Create your account</Text>
        <Text style={sf.subtitle}>Fill in your details below. No credit card required.</Text>

        <View style={sf.form}>
          <Field label="BUSINESS / COMPANY NAME *" value={businessName} onChangeText={setBusinessName}
            placeholder="Acme Corp" fieldKey="business" />
          <Field label="YOUR FULL NAME *" value={contactName} onChangeText={setContactName}
            placeholder="Jane Smith" fieldKey="name" />
          <Field label="WORK EMAIL *" value={email} onChangeText={setEmail}
            placeholder="jane@acme.com" keyboardType="email-address" autoCapitalize="none" fieldKey="email" />
          <Field label="PHONE (OPTIONAL)" value={phone} onChangeText={setPhone}
            placeholder="+1 555 000 0000" keyboardType="phone-pad" autoCapitalize="none" fieldKey="phone" />
          <Field label="PASSWORD *" value={password} onChangeText={setPassword}
            placeholder="At least 8 characters" secureTextEntry={!showPwd}
            rightIcon={showPwd ? 'eye-off' : 'eye'} onRightIcon={() => setShowPwd(!showPwd)}
            autoCapitalize="none" fieldKey="pwd" />
        </View>

        {error !== '' && (
          <View style={sf.errorBox}>
            <Ionicons name="warning" size={16} color="#F87171" />
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
            : <Text style={sf.submitText}>Create Account &amp; Start Trial</Text>}
        </TouchableOpacity>

        <Text style={sf.legalText}>
          By creating an account you agree to our Terms of Service and Privacy Policy.
        </Text>

        <View style={sf.loginLink}>
          <Text style={sf.loginLinkText}>Already have an account? </Text>
          <TouchableOpacity onPress={() => router.push('/(auth)/login')}>
            <Text style={sf.loginLinkBold}>Sign In</Text>
          </TouchableOpacity>
        </View>

        <View style={{ height: insets.bottom + 40 }} />
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const sf = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#050816' },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 20, paddingBottom: 12,
    borderBottomWidth: 1, borderBottomColor: '#1E293B',
  },
  headerTitle: { fontSize: 17, fontWeight: '700', color: '#F1F5F9' },
  scroll: { padding: 24 },
  planBadge: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    backgroundColor: '#0D1225', borderWidth: 1, borderRadius: 14,
    padding: 14, marginBottom: 24,
  },
  planIconBox: { width: 36, height: 36, borderRadius: 10, justifyContent: 'center', alignItems: 'center' },
  planName: { fontSize: 14, fontWeight: '700', color: '#F1F5F9' },
  planSub: { fontSize: 11, color: '#94A3B8', marginTop: 2 },
  title: { fontSize: 22, fontWeight: '800', color: '#F1F5F9', marginBottom: 6 },
  subtitle: { fontSize: 13, color: '#94A3B8', marginBottom: 24, lineHeight: 18 },
  form: { gap: 14 },
  field: { gap: 6 },
  label: { fontSize: 11, fontWeight: '700', color: '#64748B', letterSpacing: 1.2 },
  inputBox: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    backgroundColor: '#0F172A', borderWidth: 1.5, borderColor: '#1E293B',
    borderRadius: 12, paddingHorizontal: 16, paddingVertical: Platform.OS === 'ios' ? 14 : 12,
  },
  inputFocused: { borderColor: '#6366F1', backgroundColor: '#0C1322' },
  input: { flex: 1, fontSize: 15, color: '#F1F5F9', fontWeight: '500' },
  errorBox: {
    flexDirection: 'row', alignItems: 'flex-start', gap: 8,
    backgroundColor: '#1C1115', borderWidth: 1, borderColor: '#7F1D1D',
    borderRadius: 10, padding: 12, marginTop: 16,
  },
  errorText: { fontSize: 13, color: '#F87171', flex: 1, lineHeight: 18 },
  submitBtn: {
    backgroundColor: '#6366F1', borderRadius: 14, paddingVertical: 16,
    alignItems: 'center', marginTop: 20,
    shadowColor: '#6366F1', shadowOffset: { width: 0, height: 6 }, shadowOpacity: 0.4, shadowRadius: 16, elevation: 8,
  },
  submitText: { fontSize: 16, fontWeight: '700', color: '#FFF', letterSpacing: 0.3 },
  legalText: { fontSize: 11, color: '#475569', textAlign: 'center', marginTop: 14, lineHeight: 16 },
  loginLink: { flexDirection: 'row', justifyContent: 'center', marginTop: 20 },
  loginLinkText: { fontSize: 14, color: '#64748B' },
  loginLinkBold: { fontSize: 14, color: '#818CF8', fontWeight: '700' },
});
