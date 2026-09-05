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
  free: '#6B7280',
  starter: '#6366F1',
  pro: '#22D3EE',
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

  const color = (planId: string) => PLAN_COLORS[planId] || '#6366F1';

  return (
    <View style={[s.root, { paddingTop: insets.top }]}>
      {/* Header */}
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} style={s.backBtn} hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}>
          <Ionicons name="arrow-back" size={22} color="#94A3B8" />
        </TouchableOpacity>
        <Text style={s.headerTitle}>Pricing Plans</Text>
        <View style={{ width: 44 }} />
      </View>

      <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>
        {/* Heading */}
        <View style={s.hero}>
          <Text style={s.heroTitle}>Simple, transparent pricing</Text>
          <Text style={s.heroSub}>Start free. Scale as your business grows. Cancel anytime.</Text>
        </View>

        {/* Screen quantity selector */}
        {!loading && plans.length > 0 && (
          <View style={s.screensSelector}>
            <Text style={s.screensSelectorLabel}>How many screens do you need?</Text>
            <View style={s.stepper}>
              <TouchableOpacity
                style={[s.stepBtn, screenCount <= 1 && { opacity: 0.4 }]}
                onPress={() => setScreenCount(c => Math.max(1, c - 1))}
                disabled={screenCount <= 1}
              >
                <Ionicons name="remove" size={20} color="#F1F5F9" />
              </TouchableOpacity>
              <View style={s.stepCountBox}>
                <Text style={s.stepCount}>{screenCount}</Text>
                <Text style={s.stepUnit}>screen{screenCount !== 1 ? 's' : ''}</Text>
              </View>
              <TouchableOpacity
                style={s.stepBtn}
                onPress={() => setScreenCount(c => c + 1)}
              >
                <Ionicons name="add" size={20} color="#F1F5F9" />
              </TouchableOpacity>
            </View>
          </View>
        )}

        {loading && (
          <View style={s.center}>
            <ActivityIndicator color="#6366F1" size="large" />
            <Text style={s.loadingText}>Loading plans…</Text>
          </View>
        )}

        {error !== '' && !loading && (
          <View style={s.errorBox}>
            <Ionicons name="warning" size={18} color="#F87171" />
            <Text style={s.errorText}>{error}</Text>
            <TouchableOpacity onPress={load} style={s.retryBtn}>
              <Text style={s.retryText}>Retry</Text>
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
                      <Text style={s.popularText}>{plan.highlight_text || 'Most Popular'}</Text>
                    </View>
                  )}

                  <View style={[s.planIconBox, { backgroundColor: color(plan.plan_id) + '22' }]}>
                    <Ionicons
                      name={plan.plan_id === 'free' ? 'gift' : plan.plan_id === 'starter' ? 'rocket' : plan.plan_id === 'pro' ? 'flash' : 'shield-checkmark'}
                      size={22} color={color(plan.plan_id)}
                    />
                  </View>
                  <Text style={s.planName}>{plan.display_name}</Text>

                  {/* Dynamic price */}
                  <View style={s.priceRow}>
                    <Text style={s.priceAmount}>{monthly === 0 ? 'Free' : `$${monthly.toFixed(monthly % 1 === 0 ? 0 : 2)}`}</Text>
                    {monthly > 0 && <Text style={s.pricePer}>/month</Text>}
                  </View>

                  {/* Price breakdown if extra screens */}
                  {extraScreens > 0 && plan.price_per_extra_screen && plan.price_per_extra_screen > 0 ? (
                    <Text style={s.priceBreakdown}>
                      ${plan.monthly_price}/mo base + {extraScreens} extra × ${plan.price_per_extra_screen}
                    </Text>
                  ) : (
                    <Text style={s.screensIncluded}>
                      {plan.screens_included} screen{plan.screens_included !== 1 ? 's' : ''} included
                    </Text>
                  )}

                  {plan.trial_days > 0 && (
                    <Text style={s.trialBadge}>{plan.trial_days}-day free trial</Text>
                  )}

                  <View style={s.features}>
                    {plan.features.slice(0, 5).map((f, i) => (
                      <View key={i} style={s.featureRow}>
                        <Ionicons name="checkmark-circle" size={15} color="#34D399" />
                        <Text style={s.featureText}>{f}</Text>
                      </View>
                    ))}
                    {plan.features.length > 5 && (
                      <Text style={s.moreFeatures}>+{plan.features.length - 5} more features</Text>
                    )}
                  </View>

                  <TouchableOpacity
                    style={[s.ctaBtn, { backgroundColor: plan.highlight ? color(plan.plan_id) : 'transparent', borderColor: color(plan.plan_id) }]}
                    onPress={() => handleSelectPlan(plan.plan_id)}
                    activeOpacity={0.8}
                  >
                    <Text style={[s.ctaText, !plan.highlight && { color: color(plan.plan_id) }]}>
                      {plan.plan_id === 'free' ? 'Start Free' : 'Get Started'}
                    </Text>
                  </TouchableOpacity>
                </View>
              );
            })}
          </View>
        )}

        <View style={s.enterpriseNote}>
          <Ionicons name="business" size={18} color="#9CA3AF" style={{ marginRight: 8 }} />
          <Text style={s.enterpriseText}>
            Need a custom contract?{' '}
            <Text style={{ color: '#6366F1', fontWeight: '600' }}>Contact sales →</Text>
          </Text>
        </View>

        <View style={{ height: insets.bottom + 32 }} />
      </ScrollView>
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#050816' },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 20, paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: '#1E293B' },
  backBtn: { width: 44, height: 44, justifyContent: 'center' },
  headerTitle: { fontSize: 17, fontWeight: '700', color: '#F1F5F9' },
  scroll: { paddingHorizontal: 20, paddingTop: 28 },
  hero: { alignItems: 'center', marginBottom: 28 },
  heroTitle: { fontSize: 26, fontWeight: '800', color: '#F1F5F9', textAlign: 'center', letterSpacing: -0.5, marginBottom: 10 },
  heroSub: { fontSize: 14, color: '#94A3B8', textAlign: 'center', lineHeight: 20, maxWidth: 340 },
  screensSelector: { backgroundColor: '#0D1225', borderWidth: 1, borderColor: '#1E293B', borderRadius: 16, padding: 20, alignItems: 'center', gap: 14, marginBottom: 24 },
  screensSelectorLabel: { fontSize: 14, fontWeight: '600', color: '#94A3B8', textAlign: 'center' },
  stepper: { flexDirection: 'row', alignItems: 'center', gap: 20 },
  stepBtn: { width: 48, height: 48, borderRadius: 24, backgroundColor: '#1E293B', justifyContent: 'center', alignItems: 'center' },
  stepCountBox: { alignItems: 'center', minWidth: 64 },
  stepCount: { fontSize: 36, fontWeight: '900', color: '#F1F5F9' },
  stepUnit: { fontSize: 12, color: '#64748B', marginTop: -2 },
  center: { alignItems: 'center', paddingVertical: 60, gap: 12 },
  loadingText: { fontSize: 13, color: '#64748B' },
  errorBox: { alignItems: 'center', backgroundColor: '#1C1115', borderWidth: 1, borderColor: '#7F1D1D', borderRadius: 12, padding: 20, gap: 8 },
  errorText: { fontSize: 13, color: '#F87171', textAlign: 'center' },
  retryBtn: { paddingVertical: 8, paddingHorizontal: 20, backgroundColor: '#1F2937', borderRadius: 8, marginTop: 4 },
  retryText: { fontSize: 13, color: '#D1D5DB', fontWeight: '600' },
  cardsContainer: { ...(Platform.OS === 'web' && SW > 860 ? { flexDirection: 'row', flexWrap: 'wrap', gap: 16, justifyContent: 'center' } : { gap: 16 }) },
  card: { backgroundColor: '#0D1225', borderWidth: 1, borderColor: '#1E293B', borderRadius: 20, padding: 24, ...(Platform.OS === 'web' && SW > 860 ? { width: CARD_W } : {}), position: 'relative' },
  popularBadge: { position: 'absolute', top: -12, alignSelf: 'center', paddingHorizontal: 14, paddingVertical: 4, borderRadius: 20 },
  popularText: { fontSize: 11, fontWeight: '700', color: '#FFF', letterSpacing: 0.5 },
  planIconBox: { width: 44, height: 44, borderRadius: 12, justifyContent: 'center', alignItems: 'center', marginBottom: 14 },
  planName: { fontSize: 18, fontWeight: '700', color: '#F1F5F9', marginBottom: 8 },
  priceRow: { flexDirection: 'row', alignItems: 'baseline', gap: 4, marginBottom: 2 },
  priceAmount: { fontSize: 32, fontWeight: '800', color: '#F1F5F9' },
  pricePer: { fontSize: 14, color: '#94A3B8', fontWeight: '500' },
  priceBreakdown: { fontSize: 11, color: '#F59E0B', marginBottom: 4 },
  screensIncluded: { fontSize: 12, color: '#64748B', marginBottom: 4 },
  trialBadge: { fontSize: 12, color: '#34D399', fontWeight: '600', marginBottom: 16 },
  features: { gap: 8, marginBottom: 20, marginTop: 12 },
  featureRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 8 },
  featureText: { fontSize: 13, color: '#CBD5E1', flex: 1, lineHeight: 18 },
  moreFeatures: { fontSize: 12, color: '#64748B', marginTop: 4 },
  ctaBtn: { paddingVertical: 14, borderRadius: 12, alignItems: 'center', borderWidth: 1.5, marginTop: 'auto' },
  ctaText: { fontSize: 15, fontWeight: '700', color: '#FFF' },
  enterpriseNote: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', backgroundColor: '#0D1225', borderWidth: 1, borderColor: '#1E293B', borderRadius: 12, padding: 16, marginTop: 24 },
  enterpriseText: { fontSize: 13, color: '#94A3B8', flex: 1 },
});
