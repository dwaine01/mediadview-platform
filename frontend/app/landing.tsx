import React, { useEffect, useState } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, StyleSheet,
  Dimensions, Platform, ActivityIndicator, Image,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { plansAPI } from '../src/services/api';
import type { Plan } from '../src/types';

const { width: SW } = Dimensions.get('window');
const IS_WIDE = Platform.OS === 'web' && SW > 860;
const MEDIA_BASE = process.env.EXPO_PUBLIC_BACKEND_URL || '';

// Real MediaView screen designs, rendered inside the device frame below the hero.
const SHOTS = [
  { file: 'mv-rest-pizza.webp', label: 'Restaurantes' },
  { file: 'mv-ice-001.webp', label: 'Heladerías' },
  { file: 'mv-market-001.webp', label: 'Supermercados' },
  { file: 'mv-auto-001.webp', label: 'Talleres' },
  { file: 'mv-church-001.webp', label: 'Iglesias' },
  { file: 'mv-gym-001.webp', label: 'Gimnasios' },
];

const ENVS = [
  { file: 'mv-hero-002-sm.webp', label: 'Muro de menús en restaurante' },
  { file: 'mv-env-icecream-sm.webp', label: 'Pantalla vertical · heladería' },
  { file: 'mv-env-auto-sm.webp', label: 'Sala de espera de taller' },
  { file: 'mv-env-retail-sm.webp', label: 'Vidriera comercial' },
];

const FEATURES = [
  {
    icon: 'tv' as const,
    color: '#06B6D4',
    title: 'Pantallas Conectadas',
    desc: 'Conecta cualquier TV o monitor en segundos con un código de 6 dígitos.',
  },
  {
    icon: 'fast-food' as const,
    color: '#22D3EE',
    title: 'Menús Digitales',
    desc: 'Crea y actualiza menús hermosos con precios e imágenes en tiempo real.',
  },
  {
    icon: 'calendar' as const,
    color: '#10B981',
    title: 'Programación Inteligente',
    desc: 'Muestra el contenido correcto en el momento correcto, automáticamente.',
  },
  {
    icon: 'bar-chart' as const,
    color: '#F59E0B',
    title: 'Analytics en Vivo',
    desc: 'Monitorea el rendimiento de tus pantallas desde el panel de control.',
  },
];

const PLAN_COLORS: Record<string, string> = {
  free: '#6B7280',
  starter: '#06B6D4',
  pro: '#22D3EE',
  enterprise: '#F59E0B',
};

export default function LandingPage() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [plans, setPlans] = useState<Plan[]>([]);
  const [loadingPlans, setLoadingPlans] = useState(true);
  const [shot, setShot] = useState(0);

  // Rotate the screen preview so the hero feels alive (paused on manual pick).
  useEffect(() => {
    const t = setInterval(() => setShot(p => (p + 1) % SHOTS.length), 4000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    plansAPI.listPublic()
      .then(r => setPlans(r.data))
      .catch(() => {})
      .finally(() => setLoadingPlans(false));
  }, []);

  return (
    <View style={[s.root, { paddingTop: insets.top }]}>
      {/* ── NAV ── */}
      <View style={s.nav}>
        <View style={s.navBrand}>
          <View style={s.navLogo}><Text style={s.navLogoText}>MV</Text></View>
          <Text style={s.navName}>MediaView</Text>
        </View>
        <View style={s.navActions}>
          <TouchableOpacity onPress={() => router.push('/(auth)/login')} style={s.navLogin}>
            <Text style={s.navLoginText}>Iniciar Sesión</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={() => router.push('/(auth)/pricing')} style={s.navCta} activeOpacity={0.85}>
            <Text style={s.navCtaText}>Empezar Gratis</Text>
          </TouchableOpacity>
        </View>
      </View>

      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={s.scroll}>
        {/* ── HERO ── */}
        <View style={s.hero}>
          <View style={s.heroBadge}>
            <Ionicons name="flash" size={13} color="#06B6D4" />
            <Text style={s.heroBadgeText}>Digital Signage para Restaurantes y Negocios</Text>
          </View>
          <Text style={s.heroTitle}>
            Transforma tus Pantallas en{'\n'}
            <Text style={s.heroTitleAccent}>Herramientas de Venta</Text>
          </Text>
          <Text style={s.heroSub}>
            Conecta TV, crea menús digitales y programa contenido en minutos.{'\n'}
            Sin hardware costoso. Sin técnicos. Desde $0/mes.
          </Text>
          <View style={s.heroCtas}>
            <TouchableOpacity
              style={s.heroPrimary}
              onPress={() => router.push('/(auth)/pricing')}
              activeOpacity={0.85}
            >
              <Text style={s.heroPrimaryText}>Ver Planes y Precios</Text>
              <Ionicons name="arrow-forward" size={16} color="#fff" />
            </TouchableOpacity>
            <TouchableOpacity
              style={s.heroSecondary}
              onPress={() => router.push('/(auth)/signup')}
              activeOpacity={0.85}
            >
              <Ionicons name="play-circle" size={16} color="#06B6D4" />
              <Text style={s.heroSecondaryText}>Prueba 14 días gratis</Text>
            </TouchableOpacity>
          </View>
          {/* Live indicator */}
          <View style={s.heroStats}>
            {[
              { val: '500+', label: 'Negocios activos' },
              { val: '2,000+', label: 'Pantallas conectadas' },
              { val: '99.9%', label: 'Uptime garantizado' },
            ].map((st, i) => (
              <View key={i} style={s.heroStat}>
                <Text style={s.heroStatVal}>{st.val}</Text>
                <Text style={s.heroStatLabel}>{st.label}</Text>
              </View>
            ))}
          </View>
        </View>

        {/* ── PRODUCT VISUAL: real MediaView screens on a real TV ── */}
        <View style={s.showcase}>
          <View style={s.tvFrame}>
            <Image
              source={{ uri: `${MEDIA_BASE}/api/web/assets/${SHOTS[shot].file}` }}
              style={s.tvImage}
              resizeMode="contain"
            />
          </View>
          <View style={s.tvStand} />
          <View style={s.tvFoot} />
          <View style={s.chipRow}>
            {SHOTS.map((sh, i) => (
              <TouchableOpacity
                key={sh.file}
                style={[s.chip, i === shot && s.chipOn]}
                onPress={() => setShot(i)}
                activeOpacity={0.8}
              >
                <Text style={[s.chipText, i === shot && s.chipTextOn]}>{sh.label}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>

        {/* ── ENVIRONMENTS ── */}
        <View style={s.section}>
          <Text style={s.sectionLabel}>INSTALACIONES REALES</Text>
          <Text style={s.sectionTitle}>Así se ve MediaView{'\n'}dentro de un negocio</Text>
          <View style={[s.envGrid, IS_WIDE && s.envGridWide]}>
            {ENVS.map(env => (
              <View key={env.file} style={[s.envCard, IS_WIDE && s.envCardWide]}>
                <Image
                  source={{ uri: `${MEDIA_BASE}/api/web/assets/${env.file}` }}
                  style={s.envImage}
                  resizeMode="cover"
                />
                <Text style={s.envCap}>{env.label}</Text>
              </View>
            ))}
          </View>
        </View>
        <View style={s.section}>
          <Text style={s.sectionLabel}>CARACTERÍSTICAS</Text>
          <Text style={s.sectionTitle}>Todo lo que necesitas para{'\n'}gestionar tus pantallas</Text>
          <View style={[s.featureGrid, IS_WIDE && s.featureGridWide]}>
            {FEATURES.map((f, i) => (
              <View key={i} style={[s.featureCard, IS_WIDE && s.featureCardWide]}>
                <View style={[s.featureIcon, { backgroundColor: f.color + '22' }]}>
                  <Ionicons name={f.icon} size={24} color={f.color} />
                </View>
                <Text style={s.featureTitle}>{f.title}</Text>
                <Text style={s.featureDesc}>{f.desc}</Text>
              </View>
            ))}
          </View>
        </View>

        {/* ── HOW IT WORKS ── */}
        <View style={[s.section, s.howSection]}>
          <Text style={s.sectionLabel}>CÓMO FUNCIONA</Text>
          <Text style={s.sectionTitle}>En 3 pasos, listo para usarse</Text>
          <View style={s.steps}>
            {[
              { n: '01', icon: 'add-circle' as const, color: '#06B6D4', t: 'Crea tu cuenta', d: 'Regístrate gratis, elige tu plan y configura tu negocio en minutos.' },
              { n: '02', icon: 'tv' as const, color: '#22D3EE', t: 'Conecta tu pantalla', d: 'Ingresa el código de 6 dígitos que aparece en tu TV. Listo.' },
              { n: '03', icon: 'fast-food' as const, color: '#10B981', t: 'Publica tu menú', d: 'Crea tu menú digital con imágenes y precios. Se actualiza al instante.' },
            ].map((step, i) => (
              <View key={i} style={s.step}>
                <View style={[s.stepNum, { backgroundColor: step.color + '22', borderColor: step.color + '44' }]}>
                  <Text style={[s.stepNumText, { color: step.color }]}>{step.n}</Text>
                </View>
                <View style={s.stepBody}>
                  <Ionicons name={step.icon} size={20} color={step.color} style={{ marginBottom: 8 }} />
                  <Text style={s.stepTitle}>{step.t}</Text>
                  <Text style={s.stepDesc}>{step.d}</Text>
                </View>
              </View>
            ))}
          </View>
        </View>

        {/* ── PRICING PREVIEW ── */}
        <View style={s.section}>
          <Text style={s.sectionLabel}>PRECIOS</Text>
          <Text style={s.sectionTitle}>Planes para cada tipo de negocio</Text>
          <Text style={s.sectionSub}>Sin contratos, sin sorpresas. Cancela cuando quieras.</Text>

          {loadingPlans && (
            <View style={s.planLoading}>
              <ActivityIndicator color="#06B6D4" />
            </View>
          )}

          {!loadingPlans && (
            <View style={[s.planRow, IS_WIDE && s.planRowWide]}>
              {plans.slice(0, 4).map(plan => (
                <TouchableOpacity
                  key={plan.plan_id}
                  style={[s.planCard, plan.highlight && s.planCardHighlight]}
                  onPress={() => router.push({ pathname: '/(auth)/pricing' })}
                  activeOpacity={0.85}
                >
                  {plan.highlight && (
                    <View style={[s.planPopular, { backgroundColor: PLAN_COLORS[plan.plan_id] }]}>
                      <Text style={s.planPopularText}>Más Popular</Text>
                    </View>
                  )}
                  <Text style={[s.planName, { color: PLAN_COLORS[plan.plan_id] || '#06B6D4' }]}>
                    {plan.display_name}
                  </Text>
                  <View style={s.planPriceRow}>
                    <Text style={s.planPrice}>
                      {plan.monthly_price === 0 ? 'Gratis' : `$${plan.monthly_price}`}
                    </Text>
                    {plan.monthly_price > 0 && <Text style={s.planPricePer}>/mes</Text>}
                  </View>
                  <Text style={s.planScreens}>{plan.screens_included} pantalla{plan.screens_included !== 1 ? 's' : ''} incluida{plan.screens_included !== 1 ? 's' : ''}</Text>
                  {plan.trial_days > 0 && (
                    <Text style={s.planTrial}>{plan.trial_days} días de prueba</Text>
                  )}
                </TouchableOpacity>
              ))}
            </View>
          )}

          <TouchableOpacity style={s.viewAllPlans} onPress={() => router.push('/(auth)/pricing')} activeOpacity={0.85}>
            <Text style={s.viewAllText}>Ver todos los planes y características →</Text>
          </TouchableOpacity>
        </View>

        {/* ── CTA BOTTOM ── */}
        <View style={s.ctaBottom}>
          <Text style={s.ctaTitle}>¿Listo para modernizar{'\n'}tus pantallas?</Text>
          <Text style={s.ctaSub}>Empieza gratis hoy. Activa tu prueba de 14 días sin tarjeta de crédito.</Text>
          <TouchableOpacity style={s.ctaBtn} onPress={() => router.push('/(auth)/pricing')} activeOpacity={0.85}>
            <Text style={s.ctaBtnText}>Comenzar Ahora — Es Gratis</Text>
            <Ionicons name="arrow-forward" size={18} color="#fff" />
          </TouchableOpacity>
          <TouchableOpacity onPress={() => router.push('/(auth)/login')} style={s.ctaLoginLink}>
            <Text style={s.ctaLoginText}>¿Ya tienes cuenta? Inicia sesión →</Text>
          </TouchableOpacity>
        </View>

        <View style={{ height: insets.bottom + 40 }} />
      </ScrollView>
    </View>
  );
}

const s = StyleSheet.create({
  /* ── Product showcase (device frame + real screen artwork) ── */
  showcase: { paddingHorizontal: 20, paddingBottom: 44, width: '100%', maxWidth: 900, alignSelf: 'center' },
  tvFrame: {
    width: '100%', aspectRatio: 16 / 9.6, backgroundColor: '#0B1220',
    borderRadius: 16, padding: 12, overflow: 'hidden',
  },
  tvImage: { width: '100%', height: '100%', borderRadius: 4, backgroundColor: '#05080F' },
  tvStand: { width: 110, height: 12, backgroundColor: '#0B1220', alignSelf: 'center' },
  tvFoot: { width: 200, height: 7, backgroundColor: '#0B1220', borderRadius: 6, alignSelf: 'center' },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, justifyContent: 'center', marginTop: 20 },
  chip: {
    paddingVertical: 8, paddingHorizontal: 14, borderRadius: 100,
    borderWidth: 1, borderColor: 'rgba(255,255,255,0.14)', minHeight: 36, justifyContent: 'center',
  },
  chipOn: { backgroundColor: '#06B6D4', borderColor: '#06B6D4' },
  chipText: { fontSize: 12.5, fontWeight: '600', color: '#94A3B8' },
  chipTextOn: { color: '#04212B', fontWeight: '800' },

  /* ── Real environments gallery ── */
  envGrid: { gap: 14, marginTop: 24 },
  envGridWide: { flexDirection: 'row', flexWrap: 'wrap' },
  envCard: { borderRadius: 14, overflow: 'hidden', backgroundColor: '#16233B' },
  envCardWide: { flexBasis: '48%', flexGrow: 1 },
  envImage: { width: '100%', aspectRatio: 4 / 3 },
  envCap: { fontSize: 12.5, fontWeight: '700', color: '#E2E8F0', padding: 14 },


  root: { flex: 1, backgroundColor: '#0F172A' },
  nav: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: IS_WIDE ? 48 : 20, paddingVertical: 16,
    borderBottomWidth: 1, borderBottomColor: '#1E293B',
  },
  navBrand: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  navLogo: {
    width: 36, height: 36, borderRadius: 10,
    backgroundColor: '#06B6D4', justifyContent: 'center', alignItems: 'center',
  },
  navLogoText: { fontSize: 14, fontWeight: '800', color: '#fff' },
  navName: { fontSize: 18, fontWeight: '800', color: '#F1F5F9' },
  navActions: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  navLogin: { paddingVertical: 8, paddingHorizontal: 16 },
  navLoginText: { fontSize: 14, color: '#94A3B8', fontWeight: '600' },
  navCta: {
    backgroundColor: '#06B6D4', paddingVertical: 9, paddingHorizontal: 18,
    borderRadius: 10,
  },
  navCtaText: { fontSize: 14, fontWeight: '700', color: '#fff' },
  scroll: { paddingBottom: 0 },

  // Hero
  hero: {
    alignItems: 'center', paddingHorizontal: IS_WIDE ? 48 : 24,
    paddingTop: IS_WIDE ? 80 : 48, paddingBottom: IS_WIDE ? 72 : 48,
    borderBottomWidth: 1, borderBottomColor: '#1E293B10',
  },
  heroBadge: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    backgroundColor: '#06B6D415', borderWidth: 1, borderColor: '#06B6D430',
    paddingVertical: 6, paddingHorizontal: 14, borderRadius: 20, marginBottom: 24,
  },
  heroBadgeText: { fontSize: 12, color: '#67E8F9', fontWeight: '600' },
  heroTitle: {
    fontSize: IS_WIDE ? 52 : 32, fontWeight: '900', color: '#F1F5F9',
    textAlign: 'center', letterSpacing: -1.5, lineHeight: IS_WIDE ? 60 : 40, marginBottom: 20,
  },
  heroTitleAccent: { color: '#06B6D4' },
  heroSub: {
    fontSize: IS_WIDE ? 17 : 15, color: '#94A3B8', textAlign: 'center',
    lineHeight: IS_WIDE ? 26 : 22, maxWidth: 560, marginBottom: 36,
  },
  heroCtas: { flexDirection: IS_WIDE ? 'row' : 'column', gap: 12, marginBottom: 48, width: '100%', maxWidth: 440, alignSelf: 'center' },
  heroPrimary: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
    backgroundColor: '#06B6D4', paddingVertical: 16, paddingHorizontal: 28,
    borderRadius: 14, flex: IS_WIDE ? 1 : undefined,
  },
  heroPrimaryText: { fontSize: 15, fontWeight: '700', color: '#fff' },
  heroSecondary: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
    backgroundColor: '#06B6D415', borderWidth: 1.5, borderColor: '#06B6D4',
    paddingVertical: 16, paddingHorizontal: 28, borderRadius: 14,
    flex: IS_WIDE ? 1 : undefined,
  },
  heroSecondaryText: { fontSize: 15, fontWeight: '700', color: '#06B6D4' },
  heroStats: {
    flexDirection: 'row', gap: IS_WIDE ? 48 : 24,
    borderTopWidth: 1, borderTopColor: '#1E293B', paddingTop: 32, width: '100%', maxWidth: 560, justifyContent: 'center',
  },
  heroStat: { alignItems: 'center' },
  heroStatVal: { fontSize: IS_WIDE ? 28 : 22, fontWeight: '900', color: '#F1F5F9' },
  heroStatLabel: { fontSize: 11, color: '#64748B', textAlign: 'center' },

  // Sections
  section: { paddingHorizontal: IS_WIDE ? 48 : 24, paddingVertical: IS_WIDE ? 72 : 48 },
  howSection: { backgroundColor: '#16233B' },
  sectionLabel: { fontSize: 11, fontWeight: '700', color: '#06B6D4', letterSpacing: 2, marginBottom: 12 },
  sectionTitle: {
    fontSize: IS_WIDE ? 36 : 26, fontWeight: '800', color: '#F1F5F9',
    letterSpacing: -0.5, marginBottom: 8,
  },
  sectionSub: { fontSize: 14, color: '#94A3B8', marginBottom: 32 },

  // Features
  featureGrid: { gap: 16, marginTop: 32 },
  featureGridWide: { flexDirection: 'row', flexWrap: 'wrap' },
  featureCard: { backgroundColor: '#16233B', borderWidth: 1, borderColor: '#1E293B', borderRadius: 16, padding: 24 },
  featureCardWide: { flex: 1, minWidth: 220 },
  featureIcon: { width: 48, height: 48, borderRadius: 14, justifyContent: 'center', alignItems: 'center', marginBottom: 16 },
  featureTitle: { fontSize: 16, fontWeight: '700', color: '#F1F5F9', marginBottom: 8 },
  featureDesc: { fontSize: 13, color: '#94A3B8', lineHeight: 20 },

  // Steps
  steps: { gap: 20, marginTop: 32 },
  step: { flexDirection: 'row', gap: 16, alignItems: 'flex-start' },
  stepNum: {
    width: 52, height: 52, borderRadius: 16, borderWidth: 1,
    justifyContent: 'center', alignItems: 'center', flexShrink: 0,
  },
  stepNumText: { fontSize: 14, fontWeight: '900' },
  stepBody: { flex: 1 },
  stepTitle: { fontSize: 16, fontWeight: '700', color: '#F1F5F9', marginBottom: 6 },
  stepDesc: { fontSize: 13, color: '#94A3B8', lineHeight: 20 },

  // Pricing preview
  planLoading: { height: 120, justifyContent: 'center', alignItems: 'center' },
  planRow: { gap: 12, marginBottom: 24 },
  planRowWide: { flexDirection: 'row', flexWrap: 'wrap' },
  planCard: {
    backgroundColor: '#16233B', borderWidth: 1, borderColor: '#1E293B',
    borderRadius: 16, padding: 20, position: 'relative',
    ...(IS_WIDE ? { flex: 1, minWidth: 180 } : {}),
  },
  planCardHighlight: { borderColor: '#06B6D4', borderWidth: 2 },
  planPopular: {
    position: 'absolute', top: -11, alignSelf: 'center',
    paddingHorizontal: 12, paddingVertical: 3, borderRadius: 20,
  },
  planPopularText: { fontSize: 10, fontWeight: '700', color: '#fff' },
  planName: { fontSize: 14, fontWeight: '700', marginBottom: 6 },
  planPriceRow: { flexDirection: 'row', alignItems: 'baseline', gap: 2, marginBottom: 4 },
  planPrice: { fontSize: 26, fontWeight: '900', color: '#F1F5F9' },
  planPricePer: { fontSize: 12, color: '#64748B' },
  planScreens: { fontSize: 11, color: '#64748B', marginBottom: 4 },
  planTrial: { fontSize: 11, color: '#34D399', fontWeight: '600' },
  viewAllPlans: { alignItems: 'center', paddingVertical: 14, borderWidth: 1, borderColor: '#1E293B', borderRadius: 12 },
  viewAllText: { fontSize: 14, color: '#67E8F9', fontWeight: '600' },

  // Bottom CTA
  ctaBottom: {
    margin: IS_WIDE ? 48 : 24, borderRadius: 24,
    backgroundColor: '#16233B', borderWidth: 1, borderColor: '#06B6D430',
    padding: IS_WIDE ? 64 : 32, alignItems: 'center',
  },
  ctaTitle: { fontSize: IS_WIDE ? 36 : 26, fontWeight: '900', color: '#F1F5F9', textAlign: 'center', marginBottom: 12 },
  ctaSub: { fontSize: 14, color: '#94A3B8', textAlign: 'center', maxWidth: 400, marginBottom: 32, lineHeight: 22 },
  ctaBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    backgroundColor: '#06B6D4', paddingVertical: 18, paddingHorizontal: 36,
    borderRadius: 14, marginBottom: 16,
  },
  ctaBtnText: { fontSize: 16, fontWeight: '700', color: '#fff' },
  ctaLoginLink: { paddingVertical: 8 },
  ctaLoginText: { fontSize: 13, color: '#64748B' },
});
