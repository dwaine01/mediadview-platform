import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, ScrollView, StyleSheet, ActivityIndicator, TouchableOpacity,
  TextInput, Image, Platform, Modal, KeyboardAvoidingView,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { router, useLocalSearchParams } from 'expo-router';
import { workspaceAPI } from '../../src/services/api';
import AppDialog, { type DialogState } from '../../src/components/AppDialog';
import { formatWhen, inDays, parseWhen, windowLabel } from '../../src/utils/whenText';

const API_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';

type Item = {
  id: string; type: 'media' | 'menu'; ref_id: string; title: string; duration: number;
  // Ventana propia de este elemento. Vacío = sale siempre.
  starts_at?: string | null; ends_at?: string | null;
};

type LibraryEntry = { id: string; title: string; kind: 'media' | 'menu'; thumb?: string | null };

type Schedule = {
  mode: 'always' | 'scheduled';
  days: number[];
  start_time: string;
  end_time: string;
  timezone: string;
};

const DAYS = [
  { i: 0, label: 'L' }, { i: 1, label: 'M' }, { i: 2, label: 'M' }, { i: 3, label: 'J' },
  { i: 4, label: 'V' }, { i: 5, label: 'S' }, { i: 6, label: 'D' },
];

const PRESETS: { key: string; label: string; icon: keyof typeof Ionicons.glyphMap; start: string; end: string }[] = [
  { key: 'breakfast', label: 'Desayuno', icon: 'sunny-outline', start: '06:00', end: '11:00' },
  { key: 'lunch', label: 'Comida', icon: 'restaurant-outline', start: '11:00', end: '17:00' },
  { key: 'dinner', label: 'Cena', icon: 'moon-outline', start: '17:00', end: '23:00' },
];

/** Keeps the HH:MM shape while the user types. */
function formatTime(raw: string): string {
  const d = raw.replace(/\D/g, '').slice(0, 4);
  if (d.length <= 2) return d;
  return `${d.slice(0, 2)}:${d.slice(2)}`;
}

function isValidTime(value: string): boolean {
  const match = /^(\d{2}):(\d{2})$/.exec(value);
  if (!match) return false;
  return Number(match[1]) <= 23 && Number(match[2]) <= 59;
}

export default function PlaylistEdit() {
  const insets = useSafeAreaInsets();
  const { id } = useLocalSearchParams<{ id: string }>();

  const [name, setName] = useState('');
  const [status, setStatus] = useState('draft');
  const [items, setItems] = useState<Item[]>([]);
  const [schedule, setSchedule] = useState<Schedule>({
    mode: 'always', days: [0, 1, 2, 3, 4, 5, 6], start_time: '00:00', end_time: '23:59',
    timezone: 'America/New_York',
  });
  const [priority, setPriority] = useState(10);
  const [library, setLibrary] = useState<LibraryEntry[]>([]);
  const [showAdd, setShowAdd] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState('');
  const [dialog, setDialog] = useState<DialogState>(null);

  const load = useCallback(async () => {
    try {
      setLoading(true); setError('');
      const [plRes, mediaRes, menusRes] = await Promise.all([
        workspaceAPI.playlists(), workspaceAPI.media(), workspaceAPI.menus(),
      ]);
      const pl = (plRes.data || []).find((p: any) => p.id === id);
      if (!pl) { setError('Playlist no encontrada'); return; }
      setName(pl.name || '');
      setStatus(pl.status || 'draft');
      setSchedule({
        mode: pl.schedule?.mode === 'scheduled' ? 'scheduled' : 'always',
        days: Array.isArray(pl.schedule?.days) && pl.schedule.days.length ? pl.schedule.days : [0, 1, 2, 3, 4, 5, 6],
        start_time: pl.schedule?.start_time || '00:00',
        end_time: pl.schedule?.end_time || '23:59',
        timezone: pl.schedule?.timezone || 'America/New_York',
      });
      setPriority(Number(pl.priority) || 10);
      setItems((pl.items || []).map((it: any) => ({
        id: it.id, type: it.type, ref_id: it.ref_id,
        title: it.title || 'Contenido', duration: Number(it.duration) || 15,
        starts_at: it.starts_at || null, ends_at: it.ends_at || null,
      })));
      setLibrary([
        ...(menusRes.data || []).map((m: any) => ({ id: m.id, title: m.name || 'Menú', kind: 'menu' as const, thumb: null })),
        ...(mediaRes.data || []).map((m: any) => ({
          id: m.id, title: m.filename || 'Archivo', kind: 'media' as const,
          thumb: (m.content_type || '').startsWith('image') ? `${API_URL}/api/player/media/${m.id}` : null,
        })),
      ]);
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'No se pudo cargar');
    } finally { setLoading(false); }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  const move = (index: number, delta: number) => {
    setItems(prev => {
      const next = [...prev];
      const target = index + delta;
      if (target < 0 || target >= next.length) return prev;
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
    setDirty(true);
  };

  const setDuration = (index: number, raw: string) => {
    const digits = raw.replace(/\D/g, '').slice(0, 4);
    setItems(prev => prev.map((it, i) => i === index ? { ...it, duration: digits === '' ? 0 : Number(digits) } : it));
    setDirty(true);
  };

  const remove = (index: number) => {
    setItems(prev => prev.filter((_, i) => i !== index));
    setDirty(true);
  };

  const addFromLibrary = (entry: LibraryEntry) => {
    setItems(prev => [...prev, {
      id: `new-${Date.now()}`, type: entry.kind, ref_id: entry.id, title: entry.title, duration: 15,
    }]);
    setDirty(true);
    setShowAdd(false);
  };

  const thumbFor = (it: Item) =>
    it.type === 'media' ? `${API_URL}/api/player/media/${it.ref_id}` : null;

  // ── Programación de UN elemento ──────────────────────────────────────────
  // «Esta foto sale hasta el domingo y se apaga sola»: la ventana es del
  // elemento, no de la playlist entera.
  const [scheduling, setScheduling] = useState<number | null>(null);
  const [fromText, setFromText] = useState('');
  const [toText, setToText] = useState('');

  const openSchedule = (index: number) => {
    setFromText(formatWhen(items[index]?.starts_at));
    setToText(formatWhen(items[index]?.ends_at));
    setScheduling(index);
  };

  const applySchedule = (startsAt: string | null, endsAt: string | null) => {
    if (scheduling === null) return;
    setItems(prev => prev.map((it, i) =>
      i === scheduling ? { ...it, starts_at: startsAt, ends_at: endsAt } : it));
    setDirty(true);
    setScheduling(null);
  };

  const saveSchedule = () => {
    const startsAt = fromText.trim() ? parseWhen(fromText) : null;
    const endsAt = toText.trim() ? parseWhen(toText) : null;
    if ((fromText.trim() && !startsAt) || (toText.trim() && !endsAt)) {
      setDialog({ title: 'Fecha inválida',
                  message: 'Escribila así: 24/12/2026 18:00' });
      return;
    }
    if (startsAt && endsAt && endsAt <= startsAt) {
      setDialog({ title: 'Revisá las fechas', message: 'El fin tiene que ser después del inicio.' });
      return;
    }
    applySchedule(startsAt, endsAt);
  };

  const save = useCallback(async () => {    if (!name.trim()) { setDialog({ title: 'Ponle un nombre a la playlist' }); return; }
    if (items.some(it => it.duration < 3)) {
      setDialog({ title: 'Duración muy corta', message: 'Cada elemento debe durar al menos 3 segundos.' });
      return;
    }
    if (schedule.mode === 'scheduled') {
      if (!isValidTime(schedule.start_time) || !isValidTime(schedule.end_time)) {
        setDialog({ title: 'Horario inválido', message: 'Usa el formato de 24 horas, por ejemplo 07:00 y 11:30.' });
        return;
      }
      if (schedule.days.length === 0) {
        setDialog({ title: 'Elige al menos un día', message: 'Marca los días en los que se debe mostrar.' });
        return;
      }
    }
    setSaving(true);
    try {
      await workspaceAPI.updatePlaylist(String(id), {
        name: name.trim(),
        items: items.map(it => ({
          type: it.type, ref_id: it.ref_id, title: it.title, duration: it.duration,
          starts_at: it.starts_at || null, ends_at: it.ends_at || null,
        })),
        schedule,
        priority,
      });
      setDirty(false);
      setDialog({
        title: 'Cambios guardados',
        icon: 'checkmark-circle-outline',
        message: status === 'published'
          ? 'Tus pantallas se actualizarán en unos segundos.'
          : 'Publica la playlist cuando quieras verla en tus pantallas.',
        options: [{ label: 'Volver a Playlists', primary: true, onPress: () => router.push('/workspace/playlists') },
                  { label: 'Seguir editando' }],
      });
    } catch (e: any) {
      setDialog({ title: 'No se pudo guardar', message: e.response?.data?.detail || e.message });
    } finally { setSaving(false); }
  }, [id, name, items, status, schedule, priority]);

  const total = items.reduce((sum, it) => sum + (it.duration || 0), 0);

  return (
    <View style={pe.root}>
      <ScrollView contentContainerStyle={[pe.content, { paddingBottom: insets.bottom + 32 }]} keyboardShouldPersistTaps="handled">
        <View style={pe.header}>
          <TouchableOpacity onPress={() => router.push('/workspace/playlists')} style={pe.backBtn} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
            <Ionicons name="arrow-back" size={20} color="#64748B" />
          </TouchableOpacity>
          <View style={{ flex: 1 }}>
            <Text style={pe.title}>Editar Playlist</Text>
            <Text style={pe.sub}>
              {items.length} elemento{items.length !== 1 ? 's' : ''} · ciclo de {Math.floor(total / 60)}m {total % 60}s
              {status === 'published' ? ' · en vivo' : ' · borrador'}
            </Text>
          </View>
        </View>

        {loading && <ActivityIndicator color="#0891B2" style={{ marginTop: 40 }} />}
        {error !== '' && !loading && <Text style={pe.error}>{error}</Text>}

        {!loading && !error && (
          <>
            <Text style={pe.label}>Nombre</Text>
            <TextInput
              style={pe.input}
              value={name}
              onChangeText={(t) => { setName(t); setDirty(true); }}
              placeholder="Nombre de la playlist"
              placeholderTextColor="#CBD5E1"
            />

            <Text style={[pe.label, { marginTop: 20 }]}>Orden y duración</Text>
            {items.length === 0 && (
              <Text style={pe.emptyHint}>Esta playlist está vacía. Agrega contenido abajo.</Text>
            )}
            {items.map((it, i) => {
              const uri = thumbFor(it);
              return (
                <View key={it.id} style={pe.itemRow}>
                  <Text style={pe.pos}>{i + 1}</Text>
                  {uri
                    ? <Image source={{ uri }} style={pe.thumb} resizeMode="cover" />
                    : <View style={pe.thumbFallback}><Ionicons name="restaurant" size={16} color="#0891B2" /></View>}
                  <View style={{ flex: 1 }}>
                    <Text style={pe.itemTitle} numberOfLines={1}>{it.title}</Text>
                    <View style={pe.durRow}>
                      <TextInput
                        style={pe.durInput}
                        value={String(it.duration || '')}
                        onChangeText={(t) => setDuration(i, t)}
                        keyboardType="number-pad"
                        maxLength={4}
                      />
                      <Text style={pe.durUnit}>segundos</Text>
                    </View>
                    <TouchableOpacity
                      style={pe.whenRow}
                      onPress={() => openSchedule(i)}
                      testID={`schedule-item-${i}`}
                    >
                      <Ionicons
                        name={it.starts_at || it.ends_at ? 'alarm' : 'alarm-outline'}
                        size={14}
                        color={it.starts_at || it.ends_at ? '#B45309' : '#94A3B8'}
                      />
                      <Text style={[pe.whenText, (it.starts_at || it.ends_at) && pe.whenTextOn]}
                            numberOfLines={1}>
                        {windowLabel(it.starts_at, it.ends_at)}
                      </Text>
                    </TouchableOpacity>
                  </View>
                  <View style={pe.itemActions}>
                    <TouchableOpacity onPress={() => move(i, -1)} disabled={i === 0} style={pe.iconBtn}>
                      <Ionicons name="arrow-up" size={17} color={i === 0 ? '#CBD5E1' : '#0891B2'} />
                    </TouchableOpacity>
                    <TouchableOpacity onPress={() => move(i, 1)} disabled={i === items.length - 1} style={pe.iconBtn}>
                      <Ionicons name="arrow-down" size={17} color={i === items.length - 1 ? '#CBD5E1' : '#0891B2'} />
                    </TouchableOpacity>
                    <TouchableOpacity onPress={() => remove(i)} style={pe.iconBtn}>
                      <Ionicons name="close" size={18} color="#DC2626" />
                    </TouchableOpacity>
                  </View>
                </View>
              );
            })}

            <TouchableOpacity style={pe.addBtn} onPress={() => setShowAdd(v => !v)} activeOpacity={0.8}>
              <Ionicons name={showAdd ? 'chevron-up' : 'add'} size={16} color="#0891B2" />
              <Text style={pe.addBtnText}>{showAdd ? 'Cerrar biblioteca' : 'Agregar contenido'}</Text>
            </TouchableOpacity>

            {showAdd && library.map(l => (
              <TouchableOpacity key={`${l.kind}-${l.id}`} style={pe.libRow} onPress={() => addFromLibrary(l)} activeOpacity={0.8}>
                {l.thumb
                  ? <Image source={{ uri: l.thumb }} style={pe.thumb} resizeMode="cover" />
                  : <View style={pe.thumbFallback}><Ionicons name={l.kind === 'menu' ? 'restaurant' : 'document'} size={16} color="#0891B2" /></View>}
                <View style={{ flex: 1 }}>
                  <Text style={pe.itemTitle} numberOfLines={1}>{l.title}</Text>
                  <Text style={pe.libKind}>{l.kind === 'menu' ? 'Menú digital' : 'Imagen'}</Text>
                </View>
                <Ionicons name="add-circle-outline" size={22} color="#0891B2" />
              </TouchableOpacity>
            ))}

            <Text style={[pe.label, { marginTop: 24 }]}>¿Cuándo se muestra?</Text>
            <View style={pe.modeRow}>
              <TouchableOpacity
                style={[pe.modeBtn, schedule.mode === 'always' && pe.modeBtnOn]}
                onPress={() => { setSchedule(s => ({ ...s, mode: 'always' })); setDirty(true); }}
                activeOpacity={0.8}
              >
                <Ionicons name="infinite-outline" size={16} color={schedule.mode === 'always' ? '#0891B2' : '#94A3B8'} />
                <Text style={[pe.modeText, schedule.mode === 'always' && pe.modeTextOn]}>Todo el día</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[pe.modeBtn, schedule.mode === 'scheduled' && pe.modeBtnOn]}
                onPress={() => { setSchedule(s => ({ ...s, mode: 'scheduled' })); setDirty(true); }}
                activeOpacity={0.8}
              >
                <Ionicons name="time-outline" size={16} color={schedule.mode === 'scheduled' ? '#0891B2' : '#94A3B8'} />
                <Text style={[pe.modeText, schedule.mode === 'scheduled' && pe.modeTextOn]}>Por horario</Text>
              </TouchableOpacity>
            </View>

            {schedule.mode === 'scheduled' && (
              <View style={pe.schedBox}>
                <View style={pe.presetRow}>
                  {PRESETS.map(preset => {
                    const on = schedule.start_time === preset.start && schedule.end_time === preset.end;
                    return (
                      <TouchableOpacity
                        key={preset.key}
                        style={[pe.preset, on && pe.presetOn]}
                        onPress={() => {
                          setSchedule(s => ({ ...s, start_time: preset.start, end_time: preset.end }));
                          setDirty(true);
                        }}
                        activeOpacity={0.8}
                      >
                        <Ionicons name={preset.icon} size={15} color={on ? '#0891B2' : '#64748B'} />
                        <Text style={[pe.presetText, on && pe.presetTextOn]}>{preset.label}</Text>
                      </TouchableOpacity>
                    );
                  })}
                </View>

                <View style={pe.timeRow}>
                  <View style={{ flex: 1 }}>
                    <Text style={pe.miniLabel}>Desde</Text>
                    <TextInput
                      style={pe.timeInput}
                      value={schedule.start_time}
                      onChangeText={(t) => { setSchedule(s => ({ ...s, start_time: formatTime(t) })); setDirty(true); }}
                      placeholder="07:00"
                      placeholderTextColor="#CBD5E1"
                      keyboardType="number-pad"
                      maxLength={5}
                    />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={pe.miniLabel}>Hasta</Text>
                    <TextInput
                      style={pe.timeInput}
                      value={schedule.end_time}
                      onChangeText={(t) => { setSchedule(s => ({ ...s, end_time: formatTime(t) })); setDirty(true); }}
                      placeholder="11:00"
                      placeholderTextColor="#CBD5E1"
                      keyboardType="number-pad"
                      maxLength={5}
                    />
                  </View>
                </View>

                <Text style={pe.miniLabel}>Días</Text>
                <View style={pe.dayRow}>
                  {DAYS.map(day => {
                    const on = schedule.days.includes(day.i);
                    return (
                      <TouchableOpacity
                        key={day.i}
                        style={[pe.dayChip, on && pe.dayChipOn]}
                        onPress={() => {
                          setSchedule(s => ({
                            ...s,
                            days: on ? s.days.filter(d => d !== day.i) : [...s.days, day.i].sort(),
                          }));
                          setDirty(true);
                        }}
                        activeOpacity={0.8}
                      >
                        <Text style={[pe.dayText, on && pe.dayTextOn]}>{day.label}</Text>
                      </TouchableOpacity>
                    );
                  })}
                </View>

                <View style={pe.prioRow}>
                  <View style={{ flex: 1 }}>
                    <Text style={pe.miniLabel}>Prioridad</Text>
                    <Text style={pe.prioHint}>Si dos playlists coinciden a la misma hora, gana la de mayor prioridad.</Text>
                  </View>
                  <View style={pe.stepper}>
                    <TouchableOpacity onPress={() => { setPriority(v => Math.max(0, v - 5)); setDirty(true); }} style={pe.stepBtn}>
                      <Ionicons name="remove" size={16} color="#0891B2" />
                    </TouchableOpacity>
                    <Text style={pe.prioValue}>{priority}</Text>
                    <TouchableOpacity onPress={() => { setPriority(v => Math.min(100, v + 5)); setDirty(true); }} style={pe.stepBtn}>
                      <Ionicons name="add" size={16} color="#0891B2" />
                    </TouchableOpacity>
                  </View>
                </View>
              </View>
            )}

            <TouchableOpacity
              style={[pe.saveBtn, (!dirty || saving) && { opacity: 0.55 }]}
              onPress={save}
              disabled={!dirty || saving}
              activeOpacity={0.85}
            >
              {saving ? <ActivityIndicator color="#fff" /> : <Text style={pe.saveText}>Guardar Cambios</Text>}
            </TouchableOpacity>
          </>
        )}
      </ScrollView>

      {/* Programación de un elemento */}
      <Modal visible={scheduling !== null} transparent animationType="slide"
             onRequestClose={() => setScheduling(null)}>
        <KeyboardAvoidingView
          behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
          style={pe.schedOverlay}
        >
          <View style={pe.schedSheet}>
            <View style={pe.schedHead}>
              <Text style={pe.schedTitle} numberOfLines={1}>
                {scheduling !== null ? items[scheduling]?.title : ''}
              </Text>
              <TouchableOpacity onPress={() => setScheduling(null)} hitSlop={12}>
                <Ionicons name="close" size={22} color="#64748B" />
              </TouchableOpacity>
            </View>
            <Text style={pe.schedHint}>
              Dejá las fechas vacías para que salga siempre.
            </Text>

            <Text style={pe.label}>Empieza a salir</Text>
            <TextInput
              style={pe.input} value={fromText} onChangeText={setFromText}
              placeholder="24/12/2026 18:00" placeholderTextColor="#CBD5E1"
              testID="sched-from"
            />
            <Text style={[pe.label, { marginTop: 14 }]}>Deja de salir</Text>
            <TextInput
              style={pe.input} value={toText} onChangeText={setToText}
              placeholder="26/12/2026 23:59" placeholderTextColor="#CBD5E1"
              testID="sched-to"
            />

            <View style={pe.chipRow}>
              {[['Hoy', 0], ['3 días', 2], ['1 semana', 6]].map(([label, days]) => (
                <TouchableOpacity
                  key={String(label)}
                  style={pe.chip}
                  onPress={() => setToText(formatWhen(inDays(Number(days))))}
                  testID={`sched-quick-${days}`}
                >
                  <Text style={pe.chipText}>Hasta {String(label).toLowerCase()}</Text>
                </TouchableOpacity>
              ))}
            </View>

            <TouchableOpacity style={pe.saveBtn} onPress={saveSchedule} testID="sched-save">
              <Text style={pe.saveText}>Guardar programación</Text>
            </TouchableOpacity>
            <TouchableOpacity style={pe.schedClear} onPress={() => applySchedule(null, null)}
                              testID="sched-clear">
              <Text style={pe.schedClearText}>Quitar programación (que salga siempre)</Text>
            </TouchableOpacity>
          </View>
        </KeyboardAvoidingView>
      </Modal>

      <AppDialog state={dialog} onDismiss={() => setDialog(null)} />
    </View>
  );
}

const pe = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#F8FAFC' },
  content: { padding: 20 },
  header: { flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 18 },
  backBtn: { width: 40, height: 40, borderRadius: 12, backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#E2E8F0', alignItems: 'center', justifyContent: 'center' },
  title: { fontSize: 20, fontWeight: '800', color: '#0F172A' },
  sub: { fontSize: 12.5, color: '#64748B', marginTop: 2 },
  error: { color: '#DC2626', fontSize: 13, padding: 16 },
  label: { fontSize: 11, fontWeight: '700', color: '#64748B', letterSpacing: 0.6, textTransform: 'uppercase', marginBottom: 8 },
  input: {
    fontSize: 15, color: '#0F172A', backgroundColor: '#FFFFFF', borderWidth: 1,
    borderColor: '#E2E8F0', borderRadius: 12, padding: 14,
    ...(Platform.OS === 'web' ? ({ outlineStyle: 'none' } as any) : null),
  },
  emptyHint: { fontSize: 12.5, color: '#94A3B8', marginBottom: 8 },
  itemRow: {
    flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: '#FFFFFF',
    borderWidth: 1, borderColor: '#E2E8F0', borderRadius: 12, padding: 12, marginBottom: 8,
  },
  pos: { width: 18, fontSize: 12, fontWeight: '800', color: '#94A3B8', textAlign: 'center' },
  thumb: { width: 52, height: 40, borderRadius: 8, backgroundColor: '#E2E8F0' },
  thumbFallback: { width: 52, height: 40, borderRadius: 8, backgroundColor: '#CFFAFE', alignItems: 'center', justifyContent: 'center' },
  itemTitle: { fontSize: 13, fontWeight: '600', color: '#0F172A' },
  durRow: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 5 },
  durInput: {
    width: 56, fontSize: 13, fontWeight: '700', color: '#0F172A', textAlign: 'center',
    backgroundColor: '#F8FAFC', borderWidth: 1, borderColor: '#E2E8F0', borderRadius: 8,
    paddingVertical: 6,
    ...(Platform.OS === 'web' ? ({ outlineStyle: 'none' } as any) : null),
  },
  durUnit: { fontSize: 11.5, color: '#64748B' },
  itemActions: { flexDirection: 'row', gap: 2 },
  iconBtn: { width: 34, height: 34, borderRadius: 9, alignItems: 'center', justifyContent: 'center', backgroundColor: '#F8FAFC' },
  addBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
    backgroundColor: '#ECFEFF', borderWidth: 1, borderColor: '#CFFAFE', borderRadius: 12,
    paddingVertical: 14, marginTop: 6, marginBottom: 10, minHeight: 46,
  },
  addBtnText: { fontSize: 13.5, color: '#0E7490', fontWeight: '700' },
  libRow: {
    flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: '#FFFFFF',
    borderWidth: 1, borderColor: '#E2E8F0', borderRadius: 12, padding: 10, marginBottom: 8,
  },
  libKind: { fontSize: 11, color: '#64748B', marginTop: 2 },
  modeRow: { flexDirection: 'row', gap: 10 },
  modeBtn: {
    flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 7,
    backgroundColor: '#FFFFFF', borderWidth: 1.5, borderColor: '#E2E8F0', borderRadius: 12,
    paddingVertical: 13, minHeight: 46,
  },
  modeBtnOn: { borderColor: '#06B6D4', backgroundColor: '#ECFEFF' },
  modeText: { fontSize: 13.5, fontWeight: '700', color: '#64748B' },
  modeTextOn: { color: '#0E7490' },
  schedBox: {
    backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#E2E8F0',
    borderRadius: 14, padding: 14, marginTop: 10, gap: 12,
  },
  presetRow: { flexDirection: 'row', gap: 8, flexWrap: 'wrap' },
  preset: {
    flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: '#F8FAFC',
    borderWidth: 1, borderColor: '#E2E8F0', borderRadius: 20, paddingHorizontal: 12, paddingVertical: 9,
  },
  presetOn: { borderColor: '#06B6D4', backgroundColor: '#ECFEFF' },
  presetText: { fontSize: 12.5, fontWeight: '700', color: '#64748B' },
  presetTextOn: { color: '#0E7490' },
  timeRow: { flexDirection: 'row', gap: 12 },
  miniLabel: { fontSize: 11, fontWeight: '700', color: '#64748B', marginBottom: 6 },
  timeInput: {
    fontSize: 15, fontWeight: '700', color: '#0F172A', textAlign: 'center',
    backgroundColor: '#F8FAFC', borderWidth: 1, borderColor: '#E2E8F0', borderRadius: 10, paddingVertical: 11,
    ...(Platform.OS === 'web' ? ({ outlineStyle: 'none' } as any) : null),
  },
  dayRow: { flexDirection: 'row', gap: 6 },
  dayChip: {
    flex: 1, minHeight: 40, borderRadius: 10, alignItems: 'center', justifyContent: 'center',
    backgroundColor: '#F8FAFC', borderWidth: 1, borderColor: '#E2E8F0',
  },
  dayChipOn: { backgroundColor: '#0891B2', borderColor: '#0891B2' },
  dayText: { fontSize: 12.5, fontWeight: '700', color: '#64748B' },
  dayTextOn: { color: '#FFFFFF' },
  prioRow: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  prioHint: { fontSize: 11.5, color: '#94A3B8', lineHeight: 16 },
  stepper: { flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: '#F8FAFC', borderWidth: 1, borderColor: '#E2E8F0', borderRadius: 10, padding: 4 },
  stepBtn: { width: 34, height: 34, borderRadius: 8, alignItems: 'center', justifyContent: 'center' },
  prioValue: { fontSize: 14, fontWeight: '800', color: '#0F172A', minWidth: 26, textAlign: 'center' },
  saveBtn: { backgroundColor: '#0891B2', borderRadius: 14, paddingVertical: 16, alignItems: 'center', marginTop: 18 },
  whenRow: { flexDirection: 'row', alignItems: 'center', gap: 5, minHeight: 34, marginTop: 2 },
  whenText: { fontSize: 12, fontWeight: '700', color: '#94A3B8' },
  whenTextOn: { color: '#B45309' },
  schedOverlay: { flex: 1, justifyContent: 'flex-end', backgroundColor: 'rgba(15,23,42,0.45)' },
  schedSheet: {
    backgroundColor: '#FFFFFF', borderTopLeftRadius: 22, borderTopRightRadius: 22,
    padding: 20, paddingBottom: 34, gap: 4,
  },
  schedHead: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 4 },
  schedTitle: { flex: 1, fontSize: 16, fontWeight: '800', color: '#0F172A' },
  schedHint: { fontSize: 12.5, color: '#64748B', marginBottom: 12 },
  chipRow: { flexDirection: 'row', gap: 8, marginTop: 14, flexWrap: 'wrap' },
  chip: {
    paddingHorizontal: 12, minHeight: 40, justifyContent: 'center', borderRadius: 999,
    backgroundColor: '#F1F5F9', borderWidth: 1, borderColor: '#E2E8F0',
  },
  chipText: { fontSize: 12.5, fontWeight: '700', color: '#0F172A' },
  schedClear: { minHeight: 44, alignItems: 'center', justifyContent: 'center', marginTop: 6 },
  schedClearText: { fontSize: 13, fontWeight: '700', color: '#DC2626' },
  saveText: { color: '#FFFFFF', fontSize: 15, fontWeight: '700' },
});
