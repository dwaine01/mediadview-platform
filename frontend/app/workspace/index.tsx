import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, StyleSheet, ActivityIndicator,
  RefreshControl, useWindowDimensions,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { workspaceAPI } from '../../src/services/api';
import LiveScreens from '../../src/components/LiveScreens';
import type { WorkspaceContext } from '../../src/types';

const C = {
  bg: '#F8FAFC',
  card: '#FFFFFF',
  border: '#E2E8F0',
  text: '#0F172A',
  body: '#475569',
  muted: '#64748B',
  brand: '#0891B2',
  brandLight: '#ECFEFF',
  green: '#059669',
  greenBg: '#D1FAE5',
  amber: '#D97706',
  amberBg: '#FEF3C7',
  red: '#DC2626',
  redBg: '#FEF2F2',
};

const QUICK_ACTIONS = [
  { label: 'Agregar Pantalla', desc: 'Conectar con código de 6 dígitos', icon: 'tv' as const, color: C.brand, route: '/workspace/screens' },
  { label: 'Editar Menú', desc: 'Cambiar precios y fotos', icon: 'fast-food' as const, color: '#EA580C', route: '/workspace/menus' },
  { label: 'Subir Contenido', desc: 'Imágenes y videos', icon: 'cloud-upload' as const, color: '#0EA5E9', route: '/workspace/content' },
  { label: 'Programar', desc: 'Horarios de emisión', icon: 'calendar' as const, color: C.green, route: '/workspace/schedules' },
];

type Screen = { id: string; name?: string; location?: string; status?: string };

export default function WorkspaceDashboard() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { width } = useWindowDimensions();
  const wide = width > 860;

  const [ctx, setCtx] = useState<WorkspaceContext | null>(null);
  const [screens, setScreens] = useState<Screen[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      setError('');
      const [c, s] = await Promise.all([
        workspaceAPI.context(),
        workspaceAPI.screens().catch(() => ({ data: [] })),
      ]);
      setCtx(c.data);
      setScreens(Array.isArray(s.data) ? s.data : []);
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Error al cargar el workspace');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const org = ctx?.organization;
  const sub = ctx?.subscription;
  const plan = ctx?.plan_config;
  const stats = ctx?.stats || { screens: 0, users: 0, devices: 0 };
  const online = stats.devices_online ?? 0;
  const offline = stats.devices_offline ?? Math.max(0, (stats.devices || 0) - online);

  const allowance = plan?.screens_limit ?? plan?.screens_included ?? 0;
  const used = stats.screens || 0;
  const pct = allowance > 0 ? Math.min(100, Math.round((used / allowance) * 100)) : 0;

  const hour = new Date().getHours();
  const greeting = hour < 12 ? 'Buenos días' : hour < 18 ? 'Buenas tardes' : 'Buenas noches';

  if (loading) {
    return (
      <View style={[sd.root, sd.center]}>
        <ActivityIndicator color={C.brand} size="large" />
        <Text style={sd.loadingText}>Cargando workspace…</Text>
      </View>
    );
  }

  return (
    <ScrollView
      style={sd.root}
      contentContainerStyle={[sd.content, { paddingBottom: insets.bottom + 32 }]}
      showsVerticalScrollIndicator={false}
      refreshControl={
        <RefreshControl
          refreshing={refreshing}
          onRefresh={() => { setRefreshing(true); load(); }}
          tintColor={C.brand}
        />
      }
    >
      {error !== '' && (
        <View style={sd.errorBox}>
          <Ionicons name="warning" size={16} color={C.red} />
          <Text style={sd.errorText}>{error}</Text>
          <TouchableOpacity onPress={load} style={sd.retryBtn}><Text style={sd.retryText}>Reintentar</Text></TouchableOpacity>
        </View>
      )}

      {/* ── Welcome ── */}
      <View style={sd.welcome}>
        <View style={{ flex: 1, minWidth: 200 }}>
          <Text style={sd.greeting}>{greeting}</Text>
          <Text style={sd.orgName}>{org?.name || 'Tu Workspace'}</Text>
          {!!sub?.status && (
            <View style={sd.subRow}>
              <View style={[sd.pill, sub.status === 'trial' ? { backgroundColor: C.brandLight } : { backgroundColor: C.greenBg }]}>
                <Text style={[sd.pillText, { color: sub.status === 'trial' ? C.brand : C.green }]}>
                  {sub.status === 'trial' ? 'Prueba gratuita' : sub.status === 'active' ? 'Suscripción activa' : sub.status}
                </Text>
              </View>
              {!!sub.trial_ends_at && (
                <Text style={sd.subNote}>
                  hasta el {new Date(sub.trial_ends_at).toLocaleDateString('es-ES', { month: 'long', day: 'numeric' })}
                </Text>
              )}
            </View>
          )}
        </View>
        {!!plan && (
          <TouchableOpacity style={sd.planBadge} onPress={() => router.push('/workspace/billing')} activeOpacity={0.8}>
            <Text style={sd.planLabel}>PLAN</Text>
            <Text style={sd.planName}>{plan.display_name}</Text>
            <Text style={sd.planPrice}>{plan.monthly_price === 0 ? 'Gratis' : `$${plan.monthly_price}/mes`}</Text>
          </TouchableOpacity>
        )}
      </View>

      {/* ── Screen usage + status ── */}
      <View style={[sd.row, !wide && { flexDirection: 'column' }]}>
        <View style={[sd.card, sd.usageCard]}>
          <Text style={sd.cardTitle}>Uso de pantallas</Text>
          <Text style={sd.usageBig}>
            <Text style={{ color: C.text }}>{used}</Text>
            <Text style={sd.usageOf}>{allowance > 0 ? ` de ${allowance}` : ''}</Text>
          </Text>
          <Text style={sd.usageSub}>
            {allowance > 0
              ? `${Math.max(0, allowance - used)} pantalla${allowance - used === 1 ? '' : 's'} disponible${allowance - used === 1 ? '' : 's'} en tu plan`
              : 'Pantallas conectadas a tu cuenta'}
          </Text>
          {allowance > 0 && (
            <View style={sd.barTrack}>
              <View style={[sd.barFill, { width: `${pct}%` }]} />
            </View>
          )}
          <View style={sd.usageActions}>
            <TouchableOpacity style={sd.btnPrimary} onPress={() => router.push('/workspace/screens')} activeOpacity={0.85}>
              <Ionicons name="add" size={17} color="#FFF" />
              <Text style={sd.btnPrimaryText}>Agregar Pantalla</Text>
            </TouchableOpacity>
            <TouchableOpacity style={sd.btnGhost} onPress={() => router.push('/workspace/billing')} activeOpacity={0.7}>
              <Text style={sd.btnGhostText}>Ampliar plan</Text>
            </TouchableOpacity>
          </View>
        </View>

        <View style={[sd.card, sd.statusCard]}>
          <Text style={sd.cardTitle}>Estado de dispositivos</Text>
          <View style={sd.statusRow}>
            <View style={sd.statusItem}>
              <View style={[sd.statusDot, { backgroundColor: C.green }]} />
              <Text style={sd.statusNum}>{online}</Text>
              <Text style={sd.statusLbl}>En línea</Text>
            </View>
            <View style={sd.statusDivider} />
            <View style={sd.statusItem}>
              <View style={[sd.statusDot, { backgroundColor: '#94A3B8' }]} />
              <Text style={sd.statusNum}>{offline}</Text>
              <Text style={sd.statusLbl}>Desconectados</Text>
            </View>
            <View style={sd.statusDivider} />
            <View style={sd.statusItem}>
              <View style={[sd.statusDot, { backgroundColor: C.brand }]} />
              <Text style={sd.statusNum}>{stats.users}</Text>
              <Text style={sd.statusLbl}>Equipo</Text>
            </View>
          </View>
          {stats.devices === 0 && (
            <View style={sd.emptyHint}>
              <Ionicons name="information-circle-outline" size={16} color={C.brand} />
              <Text style={sd.emptyHintText}>
                Abre el MediaView Player en tu TV y conecta el código de 6 dígitos para ver tu primera pantalla aquí.
              </Text>
            </View>
          )}
        </View>
      </View>

      {/* ── En vivo ahora ── */}
      {screens.length > 0 && (
        <View>
          <View style={sd.liveHeader}>
            <Text style={sd.sectionTitle}>En vivo ahora</Text>
            <Text style={sd.liveHint}>Se actualiza cada 15 s</Text>
          </View>
          <LiveScreens onPressScreen={() => router.push('/workspace/screens')} />
        </View>
      )}

      {/* ── Pantallas list ── */}
      <View style={sd.card}>
        <View style={sd.cardHeaderRow}>
          <Text style={sd.cardTitle}>Tus pantallas</Text>
          <TouchableOpacity onPress={() => router.push('/workspace/screens')}>
            <Text style={sd.linkText}>Ver todas →</Text>
          </TouchableOpacity>
        </View>
        {screens.length === 0 ? (
          <View style={sd.emptyState}>
            <Ionicons name="tv-outline" size={34} color="#CBD5E1" />
            <Text style={sd.emptyTitle}>Todavía no tienes pantallas</Text>
            <Text style={sd.emptyDesc}>Conecta tu primer TV en menos de un minuto.</Text>
            <TouchableOpacity style={sd.btnPrimary} onPress={() => router.push('/workspace/screens')} activeOpacity={0.85}>
              <Ionicons name="add" size={17} color="#FFF" />
              <Text style={sd.btnPrimaryText}>Conectar pantalla</Text>
            </TouchableOpacity>
          </View>
        ) : (
          screens.slice(0, 5).map(s => (
            <TouchableOpacity
              key={s.id}
              style={sd.screenRow}
              onPress={() => router.push('/workspace/screens')}
              activeOpacity={0.7}
            >
              <View style={sd.screenIcon}><Ionicons name="tv" size={17} color={C.brand} /></View>
              <View style={{ flex: 1 }}>
                <Text style={sd.screenName} numberOfLines={1}>{s.name || 'Pantalla'}</Text>
                <Text style={sd.screenLoc} numberOfLines={1}>{s.location || 'Sin ubicación'}</Text>
              </View>
              <View style={[sd.pill, s.status === 'active' ? { backgroundColor: C.greenBg } : { backgroundColor: '#F1F5F9' }]}>
                <Text style={[sd.pillText, { color: s.status === 'active' ? C.green : C.muted }]}>
                  {s.status === 'active' ? 'Activa'
                    : s.status === 'offline' ? 'Desconectada'
                    : s.status === 'pending' ? 'Pendiente'
                    : (s.status || 'Pendiente')}
                </Text>
              </View>
              <Ionicons name="chevron-forward" size={16} color="#CBD5E1" />
            </TouchableOpacity>
          ))
        )}
      </View>

      {/* ── Quick actions ── */}
      <Text style={sd.sectionTitle}>Acciones rápidas</Text>
      <View style={sd.actionsGrid}>
        {QUICK_ACTIONS.map(a => (
          <TouchableOpacity key={a.label} style={sd.actionCard} onPress={() => router.push(a.route as any)} activeOpacity={0.75}>
            <View style={[sd.actionIcon, { backgroundColor: a.color + '18' }]}>
              <Ionicons name={a.icon} size={20} color={a.color} />
            </View>
            <Text style={sd.actionLabel}>{a.label}</Text>
            <Text style={sd.actionDesc}>{a.desc}</Text>
          </TouchableOpacity>
        ))}
      </View>
    </ScrollView>
  );
}

const shadow = {
  shadowColor: '#0F172A',
  shadowOffset: { width: 0, height: 2 },
  shadowOpacity: 0.05,
  shadowRadius: 12,
  elevation: 2,
};

const sd = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.bg },
  content: { padding: 20, gap: 16 },
  center: { alignItems: 'center', justifyContent: 'center', gap: 12 },
  loadingText: { fontSize: 13, color: C.muted },

  errorBox: { alignItems: 'center', backgroundColor: C.redBg, borderWidth: 1, borderColor: '#FECACA', borderRadius: 12, padding: 18, gap: 8 },
  errorText: { fontSize: 13, color: C.red, textAlign: 'center' },
  retryBtn: { paddingVertical: 8, paddingHorizontal: 20, backgroundColor: '#FFF', borderRadius: 8, borderWidth: 1, borderColor: '#FECACA' },
  retryText: { fontSize: 13, color: C.red, fontWeight: '600' },

  card: { backgroundColor: C.card, borderWidth: 1, borderColor: C.border, borderRadius: 16, padding: 20, ...shadow },
  cardTitle: { fontSize: 13, fontWeight: '700', color: C.muted, letterSpacing: 0.3, marginBottom: 12 },
  cardHeaderRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  linkText: { fontSize: 13, fontWeight: '700', color: C.brand },
  row: { flexDirection: 'row', gap: 16 },

  welcome: {
    flexDirection: 'row', alignItems: 'flex-start', gap: 16, flexWrap: 'wrap',
    backgroundColor: C.card, borderWidth: 1, borderColor: C.border, borderRadius: 16, padding: 22, ...shadow,
  },
  greeting: { fontSize: 12, color: C.brand, fontWeight: '700', marginBottom: 4, letterSpacing: 0.4 },
  orgName: { fontSize: 24, fontWeight: '800', color: C.text, letterSpacing: -0.5, marginBottom: 10 },
  subRow: { flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' },
  subNote: { fontSize: 12.5, color: C.muted },
  pill: { paddingVertical: 4, paddingHorizontal: 10, borderRadius: 100 },
  pillText: { fontSize: 11.5, fontWeight: '700' },
  planBadge: { backgroundColor: C.bg, borderWidth: 1, borderColor: C.border, borderRadius: 14, paddingVertical: 14, paddingHorizontal: 18, alignItems: 'center', minWidth: 110 },
  planLabel: { fontSize: 9, fontWeight: '800', color: C.muted, letterSpacing: 1.4, marginBottom: 3 },
  planName: { fontSize: 17, fontWeight: '800', color: C.brand },
  planPrice: { fontSize: 11.5, color: C.muted, marginTop: 2 },

  usageCard: { flex: 1.15, minWidth: 260 },
  usageBig: { fontSize: 40, fontWeight: '800', letterSpacing: -1.5, marginBottom: 4 },
  usageOf: { fontSize: 20, fontWeight: '700', color: C.muted },
  usageSub: { fontSize: 13, color: C.body, marginBottom: 14 },
  barTrack: { height: 8, borderRadius: 100, backgroundColor: '#F1F5F9', overflow: 'hidden', marginBottom: 18 },
  barFill: { height: 8, borderRadius: 100, backgroundColor: C.brand },
  usageActions: { flexDirection: 'row', alignItems: 'center', gap: 10, flexWrap: 'wrap' },

  btnPrimary: {
    flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: C.brand,
    paddingVertical: 12, paddingHorizontal: 18, borderRadius: 10, minHeight: 44, justifyContent: 'center',
  },
  btnPrimaryText: { fontSize: 14, fontWeight: '700', color: '#FFF' },
  btnGhost: { paddingVertical: 12, paddingHorizontal: 16, borderRadius: 10, borderWidth: 1, borderColor: C.border, minHeight: 44, justifyContent: 'center' },
  btnGhostText: { fontSize: 14, fontWeight: '600', color: C.body },

  statusCard: { flex: 1, minWidth: 260 },
  statusRow: { flexDirection: 'row', alignItems: 'center' },
  statusItem: { flex: 1, alignItems: 'center', gap: 4 },
  statusDot: { width: 9, height: 9, borderRadius: 5, marginBottom: 2 },
  statusNum: { fontSize: 28, fontWeight: '800', color: C.text, fontVariant: ['tabular-nums'] },
  statusLbl: { fontSize: 11.5, color: C.muted, fontWeight: '600' },
  statusDivider: { width: 1, height: 42, backgroundColor: C.border },
  emptyHint: { flexDirection: 'row', gap: 8, alignItems: 'flex-start', backgroundColor: C.brandLight, borderRadius: 10, padding: 12, marginTop: 16 },
  emptyHintText: { flex: 1, fontSize: 12.5, color: '#0E7490', lineHeight: 18 },

  screenRow: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 12, borderTopWidth: 1, borderTopColor: C.border, minHeight: 56 },
  screenIcon: { width: 36, height: 36, borderRadius: 10, backgroundColor: C.brandLight, alignItems: 'center', justifyContent: 'center' },
  screenName: { fontSize: 14, fontWeight: '700', color: C.text },
  screenLoc: { fontSize: 12, color: C.muted, marginTop: 1 },

  emptyState: { alignItems: 'center', paddingVertical: 26, gap: 8 },
  emptyTitle: { fontSize: 15, fontWeight: '700', color: C.text, marginTop: 4 },
  emptyDesc: { fontSize: 13, color: C.muted, marginBottom: 10, textAlign: 'center' },

  sectionTitle: { fontSize: 16, fontWeight: '800', color: C.text, marginTop: 4, letterSpacing: -0.2 },
  liveHeader: { flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 12 },
  liveHint: { fontSize: 11.5, color: C.muted },
  actionsGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 14 },
  actionCard: { flex: 1, minWidth: 150, backgroundColor: C.card, borderWidth: 1, borderColor: C.border, borderRadius: 14, padding: 18, gap: 5, ...shadow },
  actionIcon: { width: 42, height: 42, borderRadius: 12, justifyContent: 'center', alignItems: 'center', marginBottom: 6 },
  actionLabel: { fontSize: 13.5, fontWeight: '700', color: C.text },
  actionDesc: { fontSize: 11.5, color: C.muted, lineHeight: 16 },
});
