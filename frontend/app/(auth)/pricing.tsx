import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, StyleSheet,
  ActivityIndicator, useWindowDimensions, Image,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { plansAPI } from '../../src/services/api';
import type { Plan } from '../../src/types';

const MEDIA = process.env.EXPO_PUBLIC_BACKEND_URL || '';

const C = {
  bg: '#F8FAFC',
  card: '#FFFFFF',
  border: '#E2E8F0',
  navy: '#0F172A',
  navyDeep: '#020C1B',
  text: '#0F172A',
  body: '#475569',
  muted: '#64748B',
  faint: '#94A3B8',
  brand: '#06B6D4',
  brandDark: '#0891B2',
  brandLight: '#67E8F9',
  green: '#059669',
};

const PLAN_COLORS: Record<string, string> = {
  free: '#64748B',
  starter: '#0E7490',
  pro: '#06B6D4',
  enterprise: '#D97706',
};

const PLAN_ICONS: Record<string, 'gift' | 'rocket' | 'flash' | 'shield-checkmark'> = {
  free: 'gift',
  starter: 'rocket',
  pro: 'flash',
  enterprise: 'shield-checkmark',
};

const INCLUDED = [
  { icon: 'color-palette' as const, title: 'Todas las plantillas', desc: 'Menús, promos y anuncios profesionales para cada rubro' },
  { icon: 'phone-portrait' as const, title: 'Edición desde el celular', desc: 'Cambia un precio o una foto detrás del mostrador' },
  { icon: 'time' as const, title: 'Programación por horario', desc: 'Desayuno en la mañana, cena en la noche, automático' },
  { icon: 'tv' as const, title: 'Funciona en cualquier TV', desc: 'Con el MediaView Player, sin hardware especial' },
  { icon: 'cloud-upload' as const, title: 'Importa tu menú actual', desc: 'Sube tu PNG, JPG o PDF y lo volvemos editable' },
  { icon: 'lock-closed' as const, title: 'Cancela cuando quieras', desc: 'Sin contratos largos ni penalidades' },
];

const SHOWCASE = [
  { file: 'mv-rest-pizza-sm.webp', label: 'Restaurantes' },
  { file: 'mv-ice-001-sm.webp', label: 'Heladerías' },
  { file: 'mv-market-001-sm.webp', label: 'Supermercados' },
  { file: 'mv-auto-001-sm.webp', label: 'Talleres' },
  { file: 'mv-church-001-sm.webp', label: 'Iglesias' },
  { file: 'mv-gym-001-sm.webp', label: 'Gimnasios' },
];

const FAQS = [
  {
    q: '¿Necesito comprar equipo especial?',
    a: 'No. Funciona en cualquier TV con el MediaView Player. Si prefieres que nosotros instalemos pantallas LED profesionales, también lo hacemos como servicio aparte.',
  },
  {
    q: '¿Qué cuenta como una "pantalla"?',
    a: 'Cada TV o display conectado a tu cuenta cuenta como una pantalla. Si tienes un muro de 3 televisores, son 3 pantallas.',
  },
  {
    q: '¿Puedo agregar pantallas después?',
    a: 'Sí. Agregas pantallas cuando quieras y el cobro mensual se ajusta automáticamente según tu plan.',
  },
  {
    q: '¿Qué pasa cuando termina la prueba gratis?',
    a: 'Te avisamos antes. Si decides no continuar, no se te cobra nada y tu contenido queda guardado.',
  },
  {
    q: '¿Puedo cambiar de plan?',
    a: 'Sí, subes o bajas de plan en cualquier momento desde Facturación en tu panel.',
  },
  {
    q: '¿Necesito tarjeta de crédito para empezar?',
    a: 'No para el plan Free ni para iniciar la prueba gratis.',
  },
];

function calcMonthly(plan: Plan, screens: number): number {
  const extra = Math.max(0, screens - (plan.screens_included || 1));
  return plan.monthly_price + extra * (plan.price_per_extra_screen || 0);
}

function money(v: number): string {
  return `$${v.toFixed(v % 1 === 0 ? 0 : 2)}`;
}

export default function PricingScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { width } = useWindowDimensions();
  const wide = width > 900;
  const mid = width > 640;

  const [plans, setPlans] = useState<Plan[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [screenCount, setScreenCount] = useState(1);
  const [openFaq, setOpenFaq] = useState<number | null>(0);

  const load = useCallback(async () => {
    try {
      setLoading(true); setError('');
      const res = await plansAPI.listPublic();
      setPlans(res.data);
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'No se pudieron cargar los planes');
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const selectPlan = (planId: string) => {
    router.push({ pathname: '/(auth)/signup', params: { plan_id: planId, screen_count: String(screenCount) } });
  };

  const color = (planId: string) => PLAN_COLORS[planId] || C.brand;
  const cardWidth = wide ? Math.min((Math.min(width, 1240) - 40 - 60) / 4, 290) : undefined;

  return (
    <View style={s.root}>
      {/* ═══ Top bar ═══ */}
      <View style={[s.topbar, { paddingTop: insets.top + 12 }]}>
        <View style={[s.topbarInner, wide && { maxWidth: 1240 }]}>
          <TouchableOpacity onPress={() => router.back()} style={s.backBtn} hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}>
            <Ionicons name="arrow-back" size={20} color="#FFFFFF" />
          </TouchableOpacity>
          <View style={s.brandRow}>
            <View style={s.brandMark}><Text style={s.brandMarkText}>MV</Text></View>
            <Text style={s.brandName}>MediaView</Text>
          </View>
          <TouchableOpacity onPress={() => router.push('/(auth)/login')} style={s.loginBtn} activeOpacity={0.75}>
            <Text style={s.loginText}>Iniciar sesión</Text>
          </TouchableOpacity>
        </View>
      </View>

      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ paddingBottom: insets.bottom + 40 }}>
        {/* ═══ HERO BAND (navy) ═══ */}
        <View style={s.heroBand}>
          <View style={[s.wrap, wide && s.wrapWide]}>
            <View style={wide ? s.heroCols : undefined}>
              <View style={wide ? { flex: 1.1 } : undefined}>
                <Text style={s.eyebrow}>SUSCRIPCIÓN MENSUAL</Text>
                <Text style={[s.heroTitle, mid && s.heroTitleMid, wide && s.heroTitleWide]}>
                  Pagas por las pantallas{'\n'}que realmente usas
                </Text>
                <Text style={[s.heroSub, wide && { fontSize: 17 }]}>
                  Elige cuántas pantallas necesitas y el plan se ajusta. Agrega más cuando crezcas
                  y cancela cuando quieras.
                </Text>

                <View style={[s.proofRow, !mid && { flexDirection: 'column', alignItems: 'flex-start', gap: 8 }]}>
                  {['Sin hardware especial', 'Listo en menos de 5 minutos', 'Sin contratos'].map(t => (
                    <View key={t} style={s.proofItem}>
                      <Ionicons name="checkmark-circle" size={15} color={C.brandLight} />
                      <Text style={s.proofText}>{t}</Text>
                    </View>
                  ))}
                </View>
              </View>

              {wide && (
                <View style={s.heroVisual}>
                  <View style={s.tvFrame}>
                    <Image
                      source={{ uri: `${MEDIA}/api/web/assets/mv-rest-pizza.webp` }}
                      style={s.tvImg}
                      resizeMode="contain"
                    />
                  </View>
                  <View style={s.tvStand} />
                  <View style={s.tvFoot} />
                  <Text style={s.heroVisualCap}>Un menú digital real, hecho en MediaView</Text>
                </View>
              )}
            </View>

            {/* Screen selector — sits inside the band so the header has a purpose */}
            <View style={[s.selector, mid && s.selectorMid]}>
              <View style={{ flex: 1, minWidth: 200 }}>
                <Text style={s.selectorLabel}>¿CUÁNTAS PANTALLAS NECESITAS?</Text>
                <Text style={s.selectorHint}>
                  Los precios de abajo se recalculan al instante para {screenCount} pantalla{screenCount !== 1 ? 's' : ''}.
                </Text>
              </View>
              <View style={s.stepper}>
                <TouchableOpacity
                  style={[s.stepBtn, screenCount <= 1 && s.stepBtnOff]}
                  onPress={() => setScreenCount(c => Math.max(1, c - 1))}
                  disabled={screenCount <= 1}
                  activeOpacity={0.7}
                >
                  <Ionicons name="remove" size={20} color={screenCount <= 1 ? C.faint : C.text} />
                </TouchableOpacity>
                <View style={s.stepCountBox}>
                  <Text style={s.stepCount}>{screenCount}</Text>
                </View>
                <TouchableOpacity
                  style={[s.stepBtn, screenCount >= 50 && s.stepBtnOff]}
                  onPress={() => setScreenCount(c => Math.min(50, c + 1))}
                  disabled={screenCount >= 50}
                  activeOpacity={0.7}
                >
                  <Ionicons name="add" size={20} color={screenCount >= 50 ? C.faint : C.text} />
                </TouchableOpacity>
              </View>
            </View>
          </View>
        </View>

        {/* ═══ PLAN CARDS ═══ */}
        <View style={[s.wrap, wide && s.wrapWide, { marginTop: 28 }]}>
          {loading && (
            <View style={s.center}>
              <ActivityIndicator color={C.brand} size="large" />
              <Text style={s.loadingText}>Cargando planes…</Text>
            </View>
          )}

          {error !== '' && !loading && (
            <View style={s.errorBox}>
              <Ionicons name="warning" size={18} color="#DC2626" />
              <Text style={s.errorText}>{error}</Text>
              <TouchableOpacity onPress={load} style={s.retryBtn}><Text style={s.retryText}>Reintentar</Text></TouchableOpacity>
            </View>
          )}

          {!loading && plans.length > 0 && (
            <View style={[s.cards, wide && s.cardsWide]}>
              {plans.map(plan => {
                const monthly = calcMonthly(plan, screenCount);
                const extra = Math.max(0, screenCount - (plan.screens_included || 1));
                const overLimit = plan.screens_limit != null && screenCount > plan.screens_limit;
                const pc = color(plan.plan_id);
                return (
                  <View
                    key={plan.plan_id}
                    style={[
                      s.card,
                      cardWidth ? { width: cardWidth } : null,
                      plan.highlight && { borderColor: pc, borderWidth: 2 },
                      overLimit && { opacity: 0.55 },
                    ]}
                  >
                    {plan.highlight && (
                      <View style={[s.badge, { backgroundColor: pc }]}>
                        <Text style={s.badgeText}>{plan.highlight_text || 'Más Popular'}</Text>
                      </View>
                    )}

                    <View style={s.cardHead}>
                      <View style={[s.planIcon, { backgroundColor: pc + '18' }]}>
                        <Ionicons name={PLAN_ICONS[plan.plan_id] || 'flash'} size={20} color={pc} />
                      </View>
                      <Text style={s.planName}>{plan.display_name}</Text>
                    </View>

                    <View style={s.priceRow}>
                      <Text style={[s.priceAmount, { color: pc }]}>
                        {monthly === 0 ? 'Gratis' : money(monthly)}
                      </Text>
                      {monthly > 0 && <Text style={s.pricePer}>/mes</Text>}
                    </View>

                    <Text style={s.priceNote}>
                      {overLimit
                        ? `Máximo ${plan.screens_limit} pantallas en este plan`
                        : extra > 0 && plan.price_per_extra_screen > 0
                          ? `${money(plan.monthly_price)} base + ${extra} extra × ${money(plan.price_per_extra_screen)}`
                          : `${plan.screens_included} pantalla${plan.screens_included !== 1 ? 's' : ''} incluida${plan.screens_included !== 1 ? 's' : ''}`}
                    </Text>

                    {plan.trial_days > 0 && (
                      <View style={s.trialPill}>
                        <Ionicons name="gift-outline" size={12} color={C.green} />
                        <Text style={s.trialText}>{plan.trial_days} días gratis</Text>
                      </View>
                    )}

                    <View style={s.divider} />

                    <View style={s.features}>
                      {plan.features.slice(0, 6).map((f, i) => (
                        <View key={i} style={s.featureRow}>
                          <Ionicons name="checkmark" size={15} color={pc} />
                          <Text style={s.featureText}>{f}</Text>
                        </View>
                      ))}
                      {plan.features.length > 6 && (
                        <Text style={s.moreFeatures}>+{plan.features.length - 6} más</Text>
                      )}
                    </View>

                    <TouchableOpacity
                      style={[
                        s.cta,
                        plan.highlight ? { backgroundColor: pc, borderColor: pc } : { borderColor: pc },
                      ]}
                      onPress={() => selectPlan(plan.plan_id)}
                      activeOpacity={0.85}
                    >
                      <Text style={[s.ctaText, !plan.highlight && { color: pc }]}>
                        {plan.plan_id === 'free' ? 'Empezar Gratis' : 'Comenzar Ahora'}
                      </Text>
                    </TouchableOpacity>
                  </View>
                );
              })}
            </View>
          )}
        </View>

        {/* ═══ INCLUDED IN EVERY PLAN ═══ */}
        <View style={[s.wrap, wide && s.wrapWide, { marginTop: 44 }]}>
          <Text style={s.secEyebrow}>EN TODOS LOS PLANES</Text>
          <Text style={[s.secTitle, wide && { fontSize: 28 }]}>Esto viene incluido, siempre</Text>
          <View style={[s.incGrid, mid && s.incGridMid]}>
            {INCLUDED.map(item => (
              <View key={item.title} style={[s.incCard, mid && s.incCardMid, wide && s.incCardWide]}>
                <View style={s.incIcon}><Ionicons name={item.icon} size={19} color={C.brandDark} /></View>
                <Text style={s.incTitle}>{item.title}</Text>
                <Text style={s.incDesc}>{item.desc}</Text>
              </View>
            ))}
          </View>
        </View>

        {/* ═══ COMPARISON TABLE (real plan data) ═══ */}
        {!loading && plans.length > 0 && (
          <View style={[s.wrap, wide && s.wrapWide, { marginTop: 44 }]}>
            <Text style={s.secEyebrow}>COMPARACIÓN</Text>
            <Text style={[s.secTitle, wide && { fontSize: 28 }]}>Los números lado a lado</Text>
            <ScrollView
              horizontal={!wide}
              scrollEnabled={!wide}
              showsHorizontalScrollIndicator={false}
              contentContainerStyle={wide ? { width: '100%' } : { paddingBottom: 6 }}
            >
              <View style={[s.table, wide && { width: '100%', minWidth: 0 }]}>
                <View style={[s.tRow, s.tHead]}>
                  <Text style={[s.tCell, s.tCellFirst, s.tHeadText, wide && s.tCellFlexFirst]}>Detalle</Text>
                  {plans.map(p => (
                    <Text key={p.plan_id} style={[s.tCell, s.tHeadText, wide && s.tCellFlex, { color: color(p.plan_id) }]}>{p.display_name}</Text>
                  ))}
                </View>
                {([
                  ['Precio base / mes', (p: Plan) => p.monthly_price === 0 ? 'Gratis' : money(p.monthly_price)],
                  ['Pantallas incluidas', (p: Plan) => String(p.screens_included)],
                  ['Máximo de pantallas', (p: Plan) => p.screens_limit == null ? 'Ilimitado' : String(p.screens_limit)],
                  ['Pantalla extra / mes', (p: Plan) => p.price_per_extra_screen > 0 ? money(p.price_per_extra_screen) : '—'],
                  ['Prueba gratis', (p: Plan) => p.trial_days > 0 ? `${p.trial_days} días` : '—'],
                  ['Características', (p: Plan) => String(p.features.length)],
                ] as [string, (p: Plan) => string][]).map(([label, get], i) => (
                  <View key={label} style={[s.tRow, i % 2 === 1 && { backgroundColor: '#F8FAFC' }]}>
                    <Text style={[s.tCell, s.tCellFirst, s.tLabel, wide && s.tCellFlexFirst]}>{label}</Text>
                    {plans.map(p => (
                      <Text key={p.plan_id} style={[s.tCell, s.tValue, wide && s.tCellFlex]}>{get(p)}</Text>
                    ))}
                  </View>
                ))}
              </View>
            </ScrollView>
          </View>
        )}

        {/* ═══ TEMPLATE SHOWCASE ═══ */}
        <View style={[s.wrap, wide && s.wrapWide, { marginTop: 44 }]}>
          <Text style={s.secEyebrow}>PLANTILLAS INCLUIDAS</Text>
          <Text style={[s.secTitle, wide && { fontSize: 28 }]}>Diseños listos para tu rubro</Text>
          <Text style={s.secSub}>
            No empiezas de cero: eliges un diseño, cambias tus productos y tus fotos, y publicas.
          </Text>
          <View style={[s.shotGrid, mid && s.shotGridMid]}>
            {SHOWCASE.map(sh => (
              <View key={sh.file} style={[s.shotCard, mid && s.shotCardMid, wide && s.shotCardWide]}>
                <Image source={{ uri: `${MEDIA}/api/web/assets/${sh.file}` }} style={s.shotImg} resizeMode="cover" />
                <Text style={s.shotLabel}>{sh.label}</Text>
              </View>
            ))}
          </View>
        </View>

        {/* ═══ FAQ ═══ */}
        <View style={[s.wrap, wide && { maxWidth: 780, alignSelf: 'center', width: '100%' }, { marginTop: 44 }]}>
          <Text style={s.secEyebrow}>PREGUNTAS FRECUENTES</Text>
          <Text style={[s.secTitle, wide && { fontSize: 28 }]}>Antes de decidir</Text>
          <View style={{ marginTop: 20, gap: 10 }}>
            {FAQS.map((f, i) => {
              const open = openFaq === i;
              return (
                <TouchableOpacity
                  key={f.q}
                  style={[s.faq, open && s.faqOpen]}
                  onPress={() => setOpenFaq(open ? null : i)}
                  activeOpacity={0.8}
                >
                  <View style={s.faqHead}>
                    <Text style={s.faqQ}>{f.q}</Text>
                    <Ionicons name={open ? 'remove' : 'add'} size={19} color={C.brandDark} />
                  </View>
                  {open && <Text style={s.faqA}>{f.a}</Text>}
                </TouchableOpacity>
              );
            })}
          </View>
        </View>

        {/* ═══ FINAL CTA ═══ */}
        <View style={[s.wrap, wide && s.wrapWide, { marginTop: 44 }]}>
          <View style={s.ctaBand}>
            <Text style={s.ctaBandTitle}>¿Listo para que tus pantallas se vean así?</Text>
            <Text style={s.ctaBandSub}>
              Empieza gratis hoy. Conecta tu primer TV en menos de cinco minutos.
            </Text>
            <View style={[s.ctaBandBtns, !mid && { flexDirection: 'column', width: '100%' }]}>
              <TouchableOpacity style={s.ctaBandPrimary} onPress={() => selectPlan('starter')} activeOpacity={0.85}>
                <Text style={s.ctaBandPrimaryText}>Empezar ahora</Text>
              </TouchableOpacity>
              <TouchableOpacity style={s.ctaBandGhost} onPress={() => router.push('/(auth)/login')} activeOpacity={0.75}>
                <Text style={s.ctaBandGhostText}>Ya tengo cuenta</Text>
              </TouchableOpacity>
            </View>
          </View>

          <View style={s.salesNote}>
            <Ionicons name="business-outline" size={18} color={C.muted} />
            <Text style={s.salesText}>
              ¿Más de 50 pantallas o un contrato personalizado?{' '}
              <Text style={{ color: C.brandDark, fontWeight: '700' }}>Contactar ventas →</Text>
            </Text>
          </View>
        </View>
      </ScrollView>
    </View>
  );
}

const shadow = {
  shadowColor: '#0F172A',
  shadowOffset: { width: 0, height: 2 },
  shadowOpacity: 0.06,
  shadowRadius: 14,
  elevation: 2,
};

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.bg },

  /* top bar */
  topbar: { backgroundColor: C.navyDeep, paddingBottom: 12, paddingHorizontal: 20 },
  topbarInner: { flexDirection: 'row', alignItems: 'center', gap: 12, width: '100%', alignSelf: 'center' },
  backBtn: { width: 40, height: 40, borderRadius: 10, alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(255,255,255,0.08)' },
  brandRow: { flexDirection: 'row', alignItems: 'center', gap: 9, flex: 1 },
  brandMark: { width: 32, height: 32, borderRadius: 9, backgroundColor: C.brand, alignItems: 'center', justifyContent: 'center' },
  brandMarkText: { fontSize: 13, fontWeight: '900', color: '#04212B' },
  brandName: { fontSize: 16, fontWeight: '800', color: '#FFFFFF', letterSpacing: -0.3 },
  loginBtn: { paddingVertical: 10, paddingHorizontal: 14, borderRadius: 10, borderWidth: 1, borderColor: 'rgba(255,255,255,0.18)', minHeight: 40, justifyContent: 'center' },
  loginText: { fontSize: 13.5, fontWeight: '600', color: '#E2E8F0' },

  /* hero band */
  heroBand: { backgroundColor: C.navy, paddingTop: 36, paddingBottom: 40 },
  wrap: { paddingHorizontal: 20, width: '100%' },
  wrapWide: { maxWidth: 1240, alignSelf: 'center' },
  eyebrow: { fontSize: 11, fontWeight: '800', letterSpacing: 2, color: C.brandLight, marginBottom: 14 },
  heroTitle: { fontSize: 30, fontWeight: '900', color: '#FFFFFF', letterSpacing: -1, lineHeight: 36, marginBottom: 14 },
  heroTitleMid: { fontSize: 38, lineHeight: 44, letterSpacing: -1.4 },
  heroTitleWide: { fontSize: 46, lineHeight: 52, letterSpacing: -1.8 },
  heroSub: { fontSize: 15.5, color: '#94A3B8', lineHeight: 24, maxWidth: 560 },
  proofRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 20, marginTop: 22 },
  proofItem: { flexDirection: 'row', alignItems: 'center', gap: 7 },
  proofText: { fontSize: 13.5, color: '#CBD5E1', fontWeight: '500' },
  heroCols: { flexDirection: 'row', alignItems: 'center', gap: 48 },
  heroVisual: { flex: 1, maxWidth: 480 },
  tvFrame: { backgroundColor: '#0B1220', borderRadius: 14, padding: 11, aspectRatio: 16 / 9.7 },
  tvImg: { width: '100%', height: '100%', borderRadius: 4, backgroundColor: '#05080F' },
  tvStand: { width: 84, height: 11, backgroundColor: '#0B1220', alignSelf: 'center' },
  tvFoot: { width: 150, height: 6, backgroundColor: '#0B1220', borderRadius: 5, alignSelf: 'center' },
  heroVisualCap: { fontSize: 12, color: '#64748B', textAlign: 'center', marginTop: 14 },

  /* selector */
  selector: {
    marginTop: 30, backgroundColor: C.card, borderRadius: 18, padding: 20,
    gap: 18, ...shadow,
  },
  selectorMid: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 24 },
  selectorLabel: { fontSize: 11, fontWeight: '800', letterSpacing: 1.4, color: C.muted, marginBottom: 6 },
  selectorHint: { fontSize: 13.5, color: C.body, lineHeight: 19 },
  stepper: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    backgroundColor: C.bg, borderWidth: 1, borderColor: C.border, borderRadius: 14, padding: 8,
  },
  stepBtn: {
    width: 44, height: 44, borderRadius: 11, backgroundColor: C.card,
    borderWidth: 1, borderColor: C.border, alignItems: 'center', justifyContent: 'center',
  },
  stepBtnOff: { opacity: 0.45 },
  stepCountBox: { minWidth: 52, alignItems: 'center' },
  stepCount: { fontSize: 28, fontWeight: '900', color: C.text, fontVariant: ['tabular-nums'] },

  /* states */
  center: { alignItems: 'center', paddingVertical: 56, gap: 12 },
  loadingText: { fontSize: 13, color: C.muted },
  errorBox: { alignItems: 'center', backgroundColor: '#FEF2F2', borderWidth: 1, borderColor: '#FECACA', borderRadius: 14, padding: 20, gap: 8 },
  errorText: { fontSize: 13, color: '#DC2626', textAlign: 'center' },
  retryBtn: { paddingVertical: 9, paddingHorizontal: 20, backgroundColor: C.card, borderRadius: 9, borderWidth: 1, borderColor: '#FECACA' },
  retryText: { fontSize: 13, color: '#DC2626', fontWeight: '700' },

  /* plan cards */
  cards: { gap: 16 },
  cardsWide: { flexDirection: 'row', gap: 20, justifyContent: 'center', alignItems: 'stretch' },
  card: { backgroundColor: C.card, borderWidth: 1, borderColor: C.border, borderRadius: 20, padding: 22, position: 'relative', ...shadow },
  badge: { position: 'absolute', top: -12, alignSelf: 'center', paddingHorizontal: 14, paddingVertical: 5, borderRadius: 20 },
  badgeText: { fontSize: 10.5, fontWeight: '800', color: '#FFFFFF', letterSpacing: 0.6 },
  cardHead: { flexDirection: 'row', alignItems: 'center', gap: 11, marginBottom: 16, marginTop: 4 },
  planIcon: { width: 40, height: 40, borderRadius: 11, alignItems: 'center', justifyContent: 'center' },
  planName: { fontSize: 19, fontWeight: '800', color: C.text, letterSpacing: -0.4 },
  priceRow: { flexDirection: 'row', alignItems: 'baseline', gap: 5 },
  priceAmount: { fontSize: 36, fontWeight: '900', letterSpacing: -1.6 },
  pricePer: { fontSize: 14, color: C.faint, fontWeight: '600' },
  priceNote: { fontSize: 12.5, color: C.muted, marginTop: 4, lineHeight: 17 },
  trialPill: {
    flexDirection: 'row', alignItems: 'center', gap: 5, alignSelf: 'flex-start',
    backgroundColor: '#D1FAE5', borderRadius: 100, paddingVertical: 4, paddingHorizontal: 10, marginTop: 12,
  },
  trialText: { fontSize: 11.5, fontWeight: '700', color: C.green },
  divider: { height: 1, backgroundColor: C.border, marginVertical: 18 },
  features: { gap: 9, marginBottom: 20 },
  featureRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 8 },
  featureText: { fontSize: 13, color: C.body, flex: 1, lineHeight: 19 },
  moreFeatures: { fontSize: 12, color: C.faint, marginTop: 2 },
  cta: { paddingVertical: 14, borderRadius: 12, alignItems: 'center', borderWidth: 1.5, marginTop: 'auto', minHeight: 48, justifyContent: 'center' },
  ctaText: { fontSize: 14.5, fontWeight: '800', color: '#FFFFFF' },

  /* section headings */
  secEyebrow: { fontSize: 11, fontWeight: '800', letterSpacing: 2, color: C.brandDark, marginBottom: 10 },
  secTitle: { fontSize: 23, fontWeight: '900', color: C.text, letterSpacing: -0.8, lineHeight: 30 },
  secSub: { fontSize: 14.5, color: C.body, lineHeight: 22, marginTop: 10, maxWidth: 620 },

  /* included grid */
  incGrid: { gap: 12, marginTop: 20 },
  incGridMid: { flexDirection: 'row', flexWrap: 'wrap' },
  incCard: { backgroundColor: C.card, borderWidth: 1, borderColor: C.border, borderRadius: 16, padding: 18, gap: 5 },
  incCardMid: { flexBasis: '48%', flexGrow: 1 },
  incCardWide: { flexBasis: '31%' },
  incIcon: { width: 38, height: 38, borderRadius: 11, backgroundColor: '#ECFEFF', alignItems: 'center', justifyContent: 'center', marginBottom: 6 },
  incTitle: { fontSize: 14.5, fontWeight: '800', color: C.text },
  incDesc: { fontSize: 12.5, color: C.muted, lineHeight: 18 },

  /* comparison table */
  table: { marginTop: 20, backgroundColor: C.card, borderWidth: 1, borderColor: C.border, borderRadius: 16, overflow: 'hidden', minWidth: 620 },
  tRow: { flexDirection: 'row', alignItems: 'center', borderTopWidth: 1, borderTopColor: C.border },
  tHead: { borderTopWidth: 0, backgroundColor: '#F1F5F9' },
  tCell: { width: 120, paddingVertical: 13, paddingHorizontal: 10, fontSize: 13, textAlign: 'center' },
  tCellFirst: { width: 180, textAlign: 'left', paddingLeft: 16 },
  tCellFlex: { width: undefined, flex: 1 },
  tCellFlexFirst: { width: undefined, flex: 1.7 },
  tHeadText: { fontSize: 12.5, fontWeight: '800', color: C.text, letterSpacing: 0.2 },
  tLabel: { color: C.muted, fontWeight: '600' },
  tValue: { color: C.text, fontWeight: '700' },

  /* template showcase */
  shotGrid: { gap: 12, marginTop: 20 },
  shotGridMid: { flexDirection: 'row', flexWrap: 'wrap' },
  shotCard: { backgroundColor: C.card, borderWidth: 1, borderColor: C.border, borderRadius: 14, overflow: 'hidden', ...shadow },
  shotCardMid: { flexBasis: '48%', flexGrow: 1 },
  shotCardWide: { flexBasis: '31%' },
  shotImg: { width: '100%', aspectRatio: 16 / 9, backgroundColor: '#0B1220' },
  shotLabel: { fontSize: 13, fontWeight: '700', color: C.text, padding: 13 },

  /* faq */
  faq: { backgroundColor: C.card, borderWidth: 1, borderColor: C.border, borderRadius: 14, paddingHorizontal: 18, paddingVertical: 15 },
  faqOpen: { borderColor: '#A5F3FC', backgroundColor: '#FBFEFF' },
  faqHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 14 },
  faqQ: { flex: 1, fontSize: 14.5, fontWeight: '700', color: C.text, lineHeight: 21 },
  faqA: { fontSize: 13.5, color: C.body, lineHeight: 21, marginTop: 11 },

  /* final cta */
  ctaBand: { backgroundColor: C.navy, borderRadius: 22, padding: 30, alignItems: 'center', gap: 12 },
  ctaBandTitle: { fontSize: 22, fontWeight: '900', color: '#FFFFFF', textAlign: 'center', letterSpacing: -0.7, lineHeight: 29 },
  ctaBandSub: { fontSize: 14.5, color: '#94A3B8', textAlign: 'center', lineHeight: 21, maxWidth: 420 },
  ctaBandBtns: { flexDirection: 'row', gap: 12, marginTop: 10 },
  ctaBandPrimary: { backgroundColor: C.brand, paddingVertical: 14, paddingHorizontal: 26, borderRadius: 12, minHeight: 48, justifyContent: 'center', alignItems: 'center' },
  ctaBandPrimaryText: { fontSize: 15, fontWeight: '800', color: '#04212B' },
  ctaBandGhost: { borderWidth: 1, borderColor: 'rgba(255,255,255,0.2)', paddingVertical: 14, paddingHorizontal: 22, borderRadius: 12, minHeight: 48, justifyContent: 'center', alignItems: 'center' },
  ctaBandGhostText: { fontSize: 15, fontWeight: '600', color: '#E2E8F0' },
  salesNote: {
    flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 18,
    backgroundColor: C.card, borderWidth: 1, borderColor: C.border, borderRadius: 14, padding: 16,
  },
  salesText: { flex: 1, fontSize: 13.5, color: C.body, lineHeight: 20 },
});
