import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, ScrollView, StyleSheet, ActivityIndicator, TouchableOpacity, RefreshControl,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { workspaceAPI } from '../../src/services/api';

type Report = {
  period: { label: string; is_current_week: boolean; days_counted: number };
  totals: { plays: number; minutes_on_air: number; screens: number; screens_offline: number; changes: number };
  top_content: { title: string; kind: string; plays: number; minutes: number }[];
  changes: { action: string; label: string; count: number }[];
  price_changes: { item?: string; from?: number; to?: number; who?: string; at?: string }[];
  team: { user_email: string; actions: number }[];
  screens: {
    screen_id: string; screen_name: string; plays: number; minutes: number;
    active_days: number; silent_days: number; is_online: boolean;
    last_seen_seconds?: number | null; never_connected: boolean;
  }[];
};

function lastSeen(seconds?: number | null): string {
  if (seconds === null || seconds === undefined) return 'nunca se conectó';
  if (seconds < 60) return `hace ${seconds}s`;
  if (seconds < 3600) return `hace ${Math.round(seconds / 60)} min`;
  if (seconds < 86400) return `hace ${Math.round(seconds / 3600)} h`;
  return `hace ${Math.round(seconds / 86400)} días`;
}

function hours(minutes: number): string {
  if (minutes < 60) return `${Math.round(minutes)} min`;
  return `${(minutes / 60).toFixed(1)} h`;
}

export default function WorkspaceReports() {
  const insets = useSafeAreaInsets();
  const [weeksAgo, setWeeksAgo] = useState(0);
  const [report, setReport] = useState<Report | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async (offset: number, isRefresh = false) => {
    try {
      if (isRefresh) setRefreshing(true); else setLoading(true);
      setError('');
      const res = await workspaceAPI.weeklyReport(offset);
      setReport(res.data);
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'No se pudo cargar el reporte');
    } finally { setRefreshing(false); setLoading(false); }
  }, []);

  useEffect(() => { load(weeksAgo); }, [load, weeksAgo]);

  const offline = report?.screens.filter(s => !s.is_online) || [];

  return (
    <ScrollView
      style={rp.root}
      contentContainerStyle={[rp.content, { paddingBottom: insets.bottom + 28 }]}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => load(weeksAgo, true)} tintColor="#0891B2" />}
    >
      <View>
        <Text style={rp.title}>Reporte Semanal</Text>
        <Text style={rp.sub}>Qué se mostró, qué cambió y qué pantallas estuvieron caídas</Text>
      </View>

      <View style={rp.weekRow}>
        {[0, 1, 2].map(offset => {
          const on = weeksAgo === offset;
          const label = offset === 0 ? 'Esta semana' : offset === 1 ? 'Semana pasada' : 'Hace 2 semanas';
          return (
            <TouchableOpacity key={offset} style={[rp.weekBtn, on && rp.weekBtnOn]} onPress={() => setWeeksAgo(offset)} activeOpacity={0.8}>
              <Text style={[rp.weekText, on && rp.weekTextOn]}>{label}</Text>
            </TouchableOpacity>
          );
        })}
      </View>

      {loading && <ActivityIndicator color="#0891B2" style={{ marginTop: 30 }} />}
      {error !== '' && !loading && <Text style={rp.error}>{error}</Text>}

      {!!report && !loading && (
        <>
          <Text style={rp.period}>
            {report.period.label}{report.period.is_current_week ? ' · en curso' : ''}
          </Text>

          <View style={rp.kpiRow}>
            <View style={rp.kpi}>
              <Text style={rp.kpiValue}>{report.totals.plays}</Text>
              <Text style={rp.kpiLabel}>reproducciones</Text>
            </View>
            <View style={rp.kpi}>
              <Text style={rp.kpiValue}>{hours(report.totals.minutes_on_air)}</Text>
              <Text style={rp.kpiLabel}>al aire</Text>
            </View>
            <View style={rp.kpi}>
              <Text style={[rp.kpiValue, report.totals.screens_offline > 0 && { color: '#DC2626' }]}>
                {report.totals.screens_offline}/{report.totals.screens}
              </Text>
              <Text style={rp.kpiLabel}>pantallas caídas</Text>
            </View>
            <View style={rp.kpi}>
              <Text style={rp.kpiValue}>{report.totals.changes}</Text>
              <Text style={rp.kpiLabel}>cambios</Text>
            </View>
          </View>

          <Text style={rp.section}>Lo más mostrado</Text>
          {report.top_content.length === 0 ? (
            <Text style={rp.empty}>Todavía no hay reproducciones registradas en esta semana.</Text>
          ) : report.top_content.map((row, i) => (
            <View key={`${row.title}-${i}`} style={rp.row}>
              <View style={rp.rowIcon}>
                <Ionicons name={row.kind === 'menu' ? 'restaurant-outline' : 'image-outline'} size={16} color="#0891B2" />
              </View>
              <Text style={rp.rowTitle} numberOfLines={1}>{row.title}</Text>
              <Text style={rp.rowValue}>{row.plays} veces · {hours(row.minutes)}</Text>
            </View>
          ))}

          <Text style={rp.section}>Pantallas caídas</Text>
          {offline.length === 0 ? (
            <View style={rp.goodBox}>
              <Ionicons name="checkmark-circle" size={18} color="#059669" />
              <Text style={rp.goodText}>Todas tus pantallas estuvieron en línea. ¡Bien!</Text>
            </View>
          ) : offline.map(screen => (
            <View key={screen.screen_id} style={rp.row}>
              <View style={[rp.rowIcon, { backgroundColor: '#FEF2F2' }]}>
                <Ionicons name="tv-outline" size={16} color="#DC2626" />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={rp.rowTitle} numberOfLines={1}>{screen.screen_name}</Text>
                <Text style={rp.rowSub}>
                  Última señal {lastSeen(screen.last_seen_seconds)}
                  {screen.silent_days > 0 ? ` · ${screen.silent_days} día(s) sin reproducir` : ''}
                </Text>
              </View>
            </View>
          ))}

          <Text style={rp.section}>Cambios del equipo</Text>
          {report.changes.length === 0 ? (
            <Text style={rp.empty}>Sin cambios registrados en esta semana.</Text>
          ) : report.changes.map(change => (
            <View key={change.action} style={rp.row}>
              <View style={rp.rowIcon}><Ionicons name="create-outline" size={16} color="#0891B2" /></View>
              <Text style={rp.rowTitle}>{change.label}</Text>
              <Text style={rp.rowValue}>{change.count}</Text>
            </View>
          ))}

          {report.price_changes.length > 0 && (
            <>
              <Text style={rp.section}>Precios que cambiaron</Text>
              {report.price_changes.map((change, i) => (
                <View key={i} style={rp.row}>
                  <View style={[rp.rowIcon, { backgroundColor: '#FFF7ED' }]}>
                    <Ionicons name="pricetag-outline" size={16} color="#EA580C" />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={rp.rowTitle} numberOfLines={1}>{change.item || 'Producto'}</Text>
                    <Text style={rp.rowSub}>{change.who}</Text>
                  </View>
                  <Text style={rp.rowValue}>
                    ${Number(change.from || 0).toFixed(2)} → ${Number(change.to || 0).toFixed(2)}
                  </Text>
                </View>
              ))}
            </>
          )}

          {report.team.length > 0 && (
            <>
              <Text style={rp.section}>Quién trabajó</Text>
              {report.team.map(member => (
                <View key={member.user_email} style={rp.row}>
                  <View style={rp.rowIcon}><Ionicons name="person-outline" size={16} color="#0891B2" /></View>
                  <Text style={rp.rowTitle} numberOfLines={1}>{member.user_email}</Text>
                  <Text style={rp.rowValue}>{member.actions} acciones</Text>
                </View>
              ))}
            </>
          )}
        </>
      )}
    </ScrollView>
  );
}

const rp = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#F8FAFC' },
  content: { padding: 20, gap: 8 },
  title: { fontSize: 22, fontWeight: '800', color: '#0F172A', marginBottom: 4 },
  sub: { fontSize: 13, color: '#64748B', lineHeight: 18 },
  weekRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 6 },
  weekBtn: {
    backgroundColor: '#FFFFFF', borderWidth: 1.5, borderColor: '#E2E8F0', borderRadius: 20,
    paddingHorizontal: 14, paddingVertical: 10, minHeight: 42, justifyContent: 'center',
  },
  weekBtnOn: { borderColor: '#06B6D4', backgroundColor: '#ECFEFF' },
  weekText: { fontSize: 12.5, fontWeight: '700', color: '#64748B' },
  weekTextOn: { color: '#0E7490' },
  period: { fontSize: 12.5, color: '#94A3B8', fontWeight: '600', marginTop: 6 },
  error: { color: '#DC2626', fontSize: 13, padding: 16 },
  kpiRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: 4 },
  kpi: {
    flexGrow: 1, flexBasis: 140, backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#E2E8F0',
    borderRadius: 14, padding: 16,
  },
  kpiValue: { fontSize: 22, fontWeight: '800', color: '#0F172A' },
  kpiLabel: { fontSize: 11.5, color: '#64748B', marginTop: 2 },
  section: { fontSize: 15, fontWeight: '800', color: '#0F172A', marginTop: 20, marginBottom: 4 },
  empty: { fontSize: 12.5, color: '#94A3B8', lineHeight: 18 },
  row: {
    flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: '#FFFFFF',
    borderWidth: 1, borderColor: '#E2E8F0', borderRadius: 12, padding: 13,
  },
  rowIcon: { width: 32, height: 32, borderRadius: 9, backgroundColor: '#ECFEFF', alignItems: 'center', justifyContent: 'center' },
  rowTitle: { fontSize: 13, fontWeight: '600', color: '#0F172A', flex: 1 },
  rowSub: { fontSize: 11, color: '#94A3B8', marginTop: 2 },
  rowValue: { fontSize: 12, fontWeight: '700', color: '#64748B' },
  goodBox: {
    flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: '#ECFDF5',
    borderWidth: 1, borderColor: '#A7F3D0', borderRadius: 12, padding: 14,
  },
  goodText: { fontSize: 13, color: '#065F46', fontWeight: '600', flex: 1 },
});
