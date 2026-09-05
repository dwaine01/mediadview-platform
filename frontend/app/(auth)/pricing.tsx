import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, StyleSheet,
  ActivityIndicator, Dimensions, Platform,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { plansAPI } from '../../src/services/api';
import type { Plan } from '../../src/types';

const { width: SW } = Dimensions.get('window');
const CARD_W = Math.min(SW - 48, 320);

const PLAN_COLORS: Record<string, string> = {
  free: '#64748B',
  starter: '#6366F1',
  pro: '#06B6D4',
  enterprise: '#F59E0B',
};

function calcMonthly(plan: Plan, screens: number): number {
  const extra = Math.max(0, screens - (plan.screens_included || 1));
  return plan.monthly_price + extra * (plan.price_per_extra_screen || 0);
}

export default function PricingScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [plans, setPlans] = useState<Plan[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [screenCount, setScreenCount] = useState(1);

  const load = useCallback(async () => {
    try {
      setLoading(true); setError('');
      const res = await plansAPI.listPublic();
      setPlans(res.data);
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Failed to load plans');
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleSelectPlan = (planId: string) => {
    router.push({ pathname: '/(auth)/signup', params: { plan_id: planId, screen_count: String(screenCount) } });
  };

  const color = (planId: string) => PLAN_COLORS[planId] || '#06B6D4';

  return (
    <View style={[s.root, { paddingTop: insets.top }]}>
      {/* Header */}
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} style={s.backBtn} hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}>
          <Ionicons name="arrow-back" size={22} color="#64748B" />
        </TouchableOpacity>
        <Text style={s.headerTitle}>Planes y Precios</Text>
        <View style={{ width: 44 }} />
      </View>

      <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>
        {/* Hero heading */}
        <View style={s.hero}>
          <Text style={s.heroTitle}>Precios simples y transparentes</Text>
          <Text style={s.heroSub}>Comienza gratis. Escala cuando tu negocio crezca. Cancela cuando quieras.</Text>
        </View>

        {/* Screen selector */}
        {!loading && plans.length > 0 && (
          <View style={s.screensSelector}>
            <Text style={s.screensSelectorLabel}>¿Cuántas pantallas necesitas?</Text>
            <View style={s.stepper}>
              <TouchableOpacity
                style={[s.stepBtn, screenCount <= 1 && { opacity: 0.4 }]}
                onPress={() => setScreenCount(c => Math.max(1, c - 1))}
                disabled={screenCount <= 1}
              >
                <Ionicons name="remove" size={20} color="#475569" />
              </TouchableOpacity>
              <View style={s.stepCountBox}>
                <Text style={s.stepCount}>{screenCount}</Text>
                <Text style={s.stepUnit}>pantalla{screenCount !== 1 ? 's' : ''}</Text>
              </View>
              <TouchableOpacity style={s.stepBtn} onPress={() => setScreenCount(c => c + 1)}>
                <Ionicons name="add" size={20} color="#475569" />
              </TouchableOpacity>
            </View>
          </View>
        )}

        {loading && (
          <View style={s.center}>
            <ActivityIndicator color="#06B6D4" size="large" />
            <Text style={s.loadingText}>Cargando planes…</Text>
          </View>
        )}

        {error !== '' && !loading && (
          <View style={s.errorBox}>
            <Ionicons name="warning" size={18} color="#EF4444" />
            <Text style={s.errorText}>{error}</Text>
            <TouchableOpacity onPress={load} style={s.retryBtn}>
              <Text style={s.retryText}>Reintentar</Text>
            </TouchableOpacity>
          </View>
        )}

        {!loading && plans.length > 0 && (
          <View style={s.cardsContainer}>
            {plans.map((plan) => {
              const monthly = calcMonthly(plan, screenCount);
              const extraScreens = Math.max(0, screenCount - (plan.screens_included || 1));
              return (
                <View key={plan.plan_id} style={[s.card, plan.highlight && { borderColor: color(plan.plan_id), borderWidth: 2 }]}>
                  {plan.highlight && (
                    <View style={[s.popularBadge, { backgroundColor: color(plan.plan_id) }]}>
                      <Text style={s.popularText}>{plan.highlight_text || 'Más Popular'}</Text>
                    </View>
                  )}

                  <View style={[s.planIconBox, { backgroundColor: color(plan.plan_id) + '15' }]}>
                    <Ionicons
                      name={plan.plan_id === 'free' ? 'gift' : plan.plan_id === 'starter' ? 'rocket' : plan.plan_id === 'pro' ? 'flash' : 'shield-checkmark'}
                      size={22} color={color(plan.plan_id)}
                    />
                  </View>
                  <Text style={s.planName}>{plan.display_name}</Text>

                  <View style={s.priceRow}>
                    <Text style={[s.priceAmount, { color: color(plan.plan_id) }]}>
                      {monthly === 0 ? 'Gratis' : `$${monthly.toFixed(monthly % 1 === 0 ? 0 : 2)}`}
                    </Text>
                    {monthly > 0 && <Text style={s.pricePer}>/mes</Text>}
                  </View>

                  {extraScreens > 0 && plan.price_per_extra_screen && plan.price_per_extra_screen > 0 ? (
                    <Text style={s.priceBreakdown}>
                      ${plan.monthly_price}/mes base + {extraScreens} extra × ${plan.price_per_extra_screen}
                    </Text>
                  ) : (
                    <Text style={s.screensIncluded}>
                      {plan.screens_included} pantalla{plan.screens_included !== 1 ? 's' : ''} incluida{plan.screens_included !== 1 ? 's' : ''}
                    </Text>
                  )}

                  {plan.trial_days > 0 && (
                    <Text style={s.trialBadge}>{plan.trial_days} días gratis de prueba</Text>
                  )}

                  <View style={s.features}>
                    {plan.features.slice(0, 5).map((f, i) => (
                      <View key={i} style={s.featureRow}>
                        <Ionicons name="checkmark-circle" size={15} color="#10B981" />
                        <Text style={s.featureText}>{f}</Text>
                      </View>
                    ))}
                    {plan.features.length > 5 && (
                      <Text style={s.moreFeatures}>+{plan.features.length - 5} más características</Text>
                    )}
                  </View>

                  <TouchableOpacity
                    style={[s.ctaBtn, { backgroundColor: plan.highlight ? color(plan.plan_id) : 'transparent', borderColor: color(plan.plan_id) }]}
                    onPress={() => handleSelectPlan(plan.plan_id)}
                    activeOpacity={0.8}
                  >
                    <Text style={[s.ctaText, !plan.highlight && { color: color(plan.plan_id) }]}>
                      {plan.plan_id === 'free' ? 'Empezar Gratis' : 'Comenzar Ahora'}
                    </Text>
                  </TouchableOpacity>
                </View>
              );
            })}
          </View>
        )}

        <View style={s.enterpriseNote}>
          <Ionicons name="business" size={18} color="#64748B" style={{ marginRight: 8 }} />
          <Text style={s.enterpriseText}>
            ¿Necesitas un contrato personalizado?{' '}
            <Text style={{ color: '#06B6D4', fontWeight: '600' }}>Contactar ventas →</Text>
          </Text>
        </View>

        <View style={{ height: insets.bottom + 32 }} />
      </ScrollView>
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#F8FAFC' },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 20, paddingVertical: 14,
    backgroundColor: '#FFFFFF',
    borderBottomWidth: 1, borderBottomColor: '#E2E8F0',
  },
  backBtn: { width: 44, height: 44, justifyContent: 'center' },
  headerTitle: { fontSize: 17, fontWeight: '700', color: '#0F172A' },
  scroll: { paddingHorizontal: 20, paddingTop: 28 },
  hero: { alignItems: 'center', marginBottom: 28 },
  heroTitle: { fontSize: 26, fontWeight: '800', color: '#0F172A', textAlign: 'center', letterSpacing: -0.5, marginBottom: 10 },
  heroSub: { fontSize: 14, color: '#475569', textAlign: 'center', lineHeight: 20, maxWidth: 340 },
  screensSelector: {
    backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#E2E8F0',
    borderRadius: 16, padding: 20, alignItems: 'center', gap: 14, marginBottom: 24,
    shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.05, shadowRadius: 8, elevation: 2,
  },
  screensSelectorLabel: { fontSize: 14, fontWeight: '600', color: '#475569', textAlign: 'center' },
  stepper: { flexDirection: 'row', alignItems: 'center', gap: 20 },
  stepBtn: {
    width: 48, height: 48, borderRadius: 24,
    backgroundColor: '#F1F5F9', justifyContent: 'center', alignItems: 'center',
    borderWidth: 1, borderColor: '#E2E8F0',
  },
  stepCountBox: { alignItems: 'center', minWidth: 64 },
  stepCount: { fontSize: 36, fontWeight: '900', color: '#0F172A' },
  stepUnit: { fontSize: 12, color: '#94A3B8', marginTop: -2 },
  center: { alignItems: 'center', paddingVertical: 60, gap: 12 },
  loadingText: { fontSize: 13, color: '#64748B' },
  errorBox: {
    alignItems: 'center', backgroundColor: '#FEF2F2',
    borderWidth: 1, borderColor: '#FECACA', borderRadius: 12, padding: 20, gap: 8,
  },
  errorText: { fontSize: 13, color: '#EF4444', textAlign: 'center' },
  retryBtn: { paddingVertical: 8, paddingHorizontal: 20, backgroundColor: '#F1F5F9', borderRadius: 8, marginTop: 4 },
  retryText: { fontSize: 13, color: '#475569', fontWeight: '600' },
  cardsContainer: {
    ...(Platform.OS === 'web' && SW > 860
      ? { flexDirection: 'row', flexWrap: 'wrap', gap: 20, justifyContent: 'center' }
      : { gap: 16 }),
  },
  card: {
    backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#E2E8F0',
    borderRadius: 20, padding: 24,
    ...(Platform.OS === 'web' && SW > 860 ? { width: CARD_W } : {}),
    position: 'relative',
    shadowColor: '#000', shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.06, shadowRadius: 16, elevation: 3,
  },
  popularBadge: {
    position: 'absolute', top: -12, alignSelf: 'center',
    paddingHorizontal: 14, paddingVertical: 4, borderRadius: 20,
  },
  popularText: { fontSize: 11, fontWeight: '700', color: '#FFF', letterSpacing: 0.5 },
  planIconBox: { width: 44, height: 44, borderRadius: 12, justifyContent: 'center', alignItems: 'center', marginBottom: 14 },
  planName: { fontSize: 18, fontWeight: '700', color: '#0F172A', marginBottom: 8 },
  priceRow: { flexDirection: 'row', alignItems: 'baseline', gap: 4, marginBottom: 2 },
  priceAmount: { fontSize: 36, fontWeight: '900' },
  pricePer: { fontSize: 14, color: '#94A3B8', fontWeight: '500' },
  priceBreakdown: { fontSize: 11, color: '#F59E0B', marginBottom: 4 },
  screensIncluded: { fontSize: 12, color: '#64748B', marginBottom: 4 },
  trialBadge: { fontSize: 12, color: '#059669', fontWeight: '600', marginBottom: 16 },
  features: { gap: 8, marginBottom: 20, marginTop: 12 },
  featureRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 8 },
  featureText: { fontSize: 13, color: '#475569', flex: 1, lineHeight: 18 },
  moreFeatures: { fontSize: 12, color: '#94A3B8', marginTop: 4 },
  ctaBtn: { paddingVertical: 14, borderRadius: 12, alignItems: 'center', borderWidth: 1.5, marginTop: 'auto' },
  ctaText: { fontSize: 15, fontWeight: '700', color: '#FFF' },
  enterpriseNote: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#E2E8F0',
    borderRadius: 12, padding: 16, marginTop: 24,
    shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.04, shadowRadius: 8, elevation: 1,
  },
  enterpriseText: { fontSize: 13, color: '#475569', flex: 1 },
});
