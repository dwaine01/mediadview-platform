import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, ScrollView, StyleSheet, ActivityIndicator, RefreshControl } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { workspaceAPI } from '../../src/services/api';
import EmptyState from '../../src/components/EmptyState';

type Event = {
  id: string; action: string; user_email?: string; resource_type?: string;
  resource_id?: string; details?: Record<string, any>; created_at?: string;
};

const META: Record<string, { icon: keyof typeof Ionicons.glyphMap; color: string; label: string }> = {
  'menu.created': { icon: 'fast-food-outline', color: '#0891B2', label: 'creó el menú' },
  'menu.updated': { icon: 'create-outline', color: '#0891B2', label: 'editó el menú' },
  'menu.deleted': { icon: 'trash-outline', color: '#DC2626', label: 'eliminó el menú' },
  'menu.published': { icon: 'tv-outline', color: '#059669', label: 'publicó el menú' },
  'menu_item.added': { icon: 'add-circle-outline', color: '#0891B2', label: 'agregó un producto' },
  'menu_item.updated': { icon: 'pricetag-outline', color: '#D97706', label: 'cambió un producto' },
  'menu_item.deleted': { icon: 'remove-circle-outline', color: '#DC2626', label: 'quitó un producto' },
  'media.uploaded': { icon: 'cloud-upload-outline', color: '#0891B2', label: 'subió contenido' },
  'playlist.created': { icon: 'list-outline', color: '#0891B2', label: 'creó una playlist' },
  'playlist.updated': { icon: 'swap-vertical-outline', color: '#D97706', label: 'editó una playlist' },
  'playlist.published': { icon: 'play-circle-outline', color: '#059669', label: 'publicó una playlist' },
  'playlist.deleted': { icon: 'trash-outline', color: '#DC2626', label: 'eliminó una playlist' },
  'screen.created': { icon: 'tv-outline', color: '#0891B2', label: 'agregó una pantalla' },
  'screen.connected': { icon: 'link-outline', color: '#059669', label: 'conectó una pantalla' },
  'org.logo_updated': { icon: 'image-outline', color: '#0891B2', label: 'cambió el logo del negocio' },
  'org.logo_removed': { icon: 'image-outline', color: '#DC2626', label: 'quitó el logo del negocio' },
  'team.member_created': { icon: 'person-add-outline', color: '#059669', label: 'agregó a alguien al equipo' },
  'team.member_updated': { icon: 'swap-horizontal-outline', color: '#D97706', label: 'cambió permisos del equipo' },
  'team.password_reset': { icon: 'key-outline', color: '#D97706', label: 'restableció una contraseña' },
  'team.member_deactivated': { icon: 'person-remove-outline', color: '#DC2626', label: 'desactivó a un miembro' },
};

function money(v: any) {
  const n = Number(v);
  return Number.isFinite(n) ? `$${n.toFixed(2)}` : String(v);
}

function detailLine(e: Event): string {
  const d = e.details || {};
  const parts: string[] = [];
  if (d.price_from !== undefined && d.price_to !== undefined) {
    parts.push(`${d.item || 'Producto'}: ${money(d.price_from)} → ${money(d.price_to)}`);
  } else if (d.item) {
    parts.push(d.price !== undefined ? `${d.item} (${money(d.price)})` : d.item);
  }
  if (d.photo_changed) parts.push('foto actualizada');
  if (d.name && !parts.length) parts.push(d.name);
  if (d.menu_name && d.item) parts.push(`en ${d.menu_name}`);
  if (d.filename) parts.push(d.filename);
  if (d.email) parts.push(d.email);
  if (d.role) parts.push(`rol: ${d.role}`);
  if (d.active === false) parts.push('desactivado');
  if (d.active === true) parts.push('reactivado');
  if (typeof d.screens === 'number') parts.push(`${d.screens} pantalla(s)`);
  return parts.join(' · ');
}

function when(iso?: string): string {
  if (!iso) return '';
  const date = new Date(iso.endsWith('Z') || iso.includes('+') ? iso : `${iso}Z`);
  const mins = Math.round((Date.now() - date.getTime()) / 60000);
  if (mins < 1) return 'ahora mismo';
  if (mins < 60) return `hace ${mins} min`;
  if (mins < 1440) return `hace ${Math.round(mins / 60)} h`;
  return date.toLocaleDateString('es-ES', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
}

export default function WorkspaceActivity() {
  const insets = useSafeAreaInsets();
  const [events, setEvents] = useState<Event[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async (isRefresh = false) => {
    try {
      if (isRefresh) setRefreshing(true); else setLoading(true);
      setError('');
      const res = await workspaceAPI.activity(80);
      setEvents(res.data || []);
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'No se pudo cargar');
    } finally { setRefreshing(false); setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <ScrollView
      style={ac.root}
      contentContainerStyle={[ac.content, { paddingBottom: insets.bottom + 24 }]}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => load(true)} tintColor="#0891B2" />}
    >
      <View>
        <Text style={ac.title}>Actividad</Text>
        <Text style={ac.sub}>Quién cambió precios, fotos, menús u horarios y cuándo</Text>
      </View>

      {loading && <ActivityIndicator color="#0891B2" style={{ marginTop: 40 }} />}
      {error !== '' && !loading && <Text style={ac.error}>{error}</Text>}

      {!loading && !error && events.length === 0 && (
        <EmptyState
          icon="time-outline"
          title="Todavía no hay movimientos"
          text="Aquí verás cada cambio de precio, foto, menú o playlist con el nombre de quien lo hizo."
        />
      )}

      {events.map(e => {
        const meta = META[e.action] || { icon: 'ellipse-outline' as const, color: '#64748B', label: e.action };
        const detail = detailLine(e);
        return (
          <View key={e.id} style={ac.row}>
            <View style={[ac.icon, { backgroundColor: `${meta.color}14` }]}>
              <Ionicons name={meta.icon} size={17} color={meta.color} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={ac.line}>
                <Text style={ac.who}>{e.user_email || 'Alguien'}</Text>
                <Text> {meta.label}</Text>
              </Text>
              {!!detail && <Text style={ac.detail}>{detail}</Text>}
            </View>
            <Text style={ac.time}>{when(e.created_at)}</Text>
          </View>
        );
      })}
    </ScrollView>
  );
}

const ac = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#F8FAFC' },
  content: { padding: 20, gap: 10 },
  title: { fontSize: 22, fontWeight: '800', color: '#0F172A', marginBottom: 4 },
  sub: { fontSize: 13, color: '#64748B', marginBottom: 8 },
  error: { color: '#DC2626', fontSize: 13, padding: 16 },
  row: {
    flexDirection: 'row', alignItems: 'flex-start', gap: 12, backgroundColor: '#FFFFFF',
    borderWidth: 1, borderColor: '#E2E8F0', borderRadius: 12, padding: 14,
  },
  icon: { width: 36, height: 36, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  line: { fontSize: 13.5, color: '#334155', lineHeight: 19 },
  who: { fontWeight: '700', color: '#0F172A' },
  detail: { fontSize: 12, color: '#64748B', marginTop: 3, lineHeight: 17 },
  time: { fontSize: 11, color: '#94A3B8', marginTop: 2 },
});
