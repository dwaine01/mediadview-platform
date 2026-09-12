/**
 * menu-canvas.tsx — «Mi propio diseño».
 *
 * El restaurante sube su menú ya diseñado (JPG, PNG o PDF) y la IA marca cada
 * nombre, cada precio y cada foto. Acá el dueño toca un recuadro y cambia el
 * texto o la foto: el diseño no se mueve, sólo el contenido. Las cajas se
 * pueden arrastrar y estirar para corregir lo que la IA no clavó.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity, TextInput, Image,
  ActivityIndicator, Modal, PanResponder, Platform, Linking, KeyboardAvoidingView,
  useWindowDimensions,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { router, useLocalSearchParams } from 'expo-router';
import * as ImagePicker from 'expo-image-picker';
import * as DocumentPicker from 'expo-document-picker';
import * as FileSystem from 'expo-file-system';
import { workspaceAPI } from '../../src/services/api';
import AppDialog, { type DialogState } from '../../src/components/AppDialog';

const API_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';
const MAX_BYTES = 20 * 1024 * 1024;

type Field = {
  id: string;
  kind: 'name' | 'price' | 'photo';
  text: string;
  original_text?: string;
  x: number; y: number; w: number; h: number;
  color: string; bg_color: string;
  font_family: string; font_weight: number; font_size: number;
  italic: boolean; uppercase: boolean;
  align: 'left' | 'center' | 'right';
  radius: number;
  image_url?: string | null;
  media_id?: string | null;
};
type Canvas = { background_url: string; width: number; height: number; fields: Field[] };

const KIND_COLOR: Record<Field['kind'], string> = {
  name: '#0891B2',
  price: '#059669',
  photo: '#7C3AED',
};
const KIND_LABEL: Record<Field['kind'], string> = {
  name: 'Texto',
  price: 'Precio',
  photo: 'Foto',
};

/** Un recuadro editable dibujado sobre el diseño, arrastrable y estirable. */
function FieldBox({
  field, scale, selected, onSelect, onGeometry,
}: {
  field: Field; scale: number; selected: boolean;
  onSelect: () => void;
  onGeometry: (patch: Partial<Field>) => void;
}) {
  const start = useRef({ x: 0, y: 0, w: 0, h: 0 });
  const accent = KIND_COLOR[field.kind];

  const move = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => true,
      onPanResponderGrant: () => {
        start.current = { x: field.x, y: field.y, w: field.w, h: field.h };
        onSelect();
      },
      onPanResponderMove: (_e, g) => {
        onGeometry({
          x: Math.max(0, Math.round(start.current.x + g.dx / scale)),
          y: Math.max(0, Math.round(start.current.y + g.dy / scale)),
        });
      },
    }),
  ).current;

  const resize = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => true,
      onPanResponderGrant: () => {
        start.current = { x: field.x, y: field.y, w: field.w, h: field.h };
        onSelect();
      },
      onPanResponderMove: (_e, g) => {
        onGeometry({
          w: Math.max(10, Math.round(start.current.w + g.dx / scale)),
          h: Math.max(10, Math.round(start.current.h + g.dy / scale)),
        });
      },
    }),
  ).current;

  return (
    <View
      {...move.panHandlers}
      style={[
        st.box,
        {
          left: field.x * scale,
          top: field.y * scale,
          width: Math.max(8, field.w * scale),
          height: Math.max(8, field.h * scale),
          borderColor: accent,
          borderWidth: selected ? 2 : 1,
          backgroundColor: selected ? `${accent}33` : `${accent}1A`,
        },
      ]}
      testID={`field-${field.id}`}
    >
      {selected && (
        <View {...resize.panHandlers} style={[st.handle, { backgroundColor: accent }]} testID={`resize-${field.id}`}>
          <Ionicons name="resize-outline" size={10} color="#fff" />
        </View>
      )}
    </View>
  );
}

export default function MenuCanvas() {
  const insets = useSafeAreaInsets();
  const { width: windowWidth } = useWindowDimensions();
  const params = useLocalSearchParams<{ id: string }>();
  const menuId = params.id;

  const [canvas, setCanvas] = useState<Canvas | null>(null);
  const [menuName, setMenuName] = useState('');
  const [loading, setLoading] = useState(true);
  const [importing, setImporting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const [draftText, setDraftText] = useState('');
  const [photoBusy, setPhotoBusy] = useState(false);
  const [dialog, setDialog] = useState<DialogState>(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const res = await workspaceAPI.getCanvas(menuId);
      setCanvas(res.data.canvas);
      setMenuName(res.data.menu_name || '');
      setDirty(false);
    } catch (e: any) {
      if (e.response?.status !== 404) {
        setDialog({ title: 'No pudimos abrir tu diseño', message: e.response?.data?.detail || e.message });
      }
      setCanvas(null);
    } finally { setLoading(false); }
  }, [menuId]);

  useEffect(() => { load(); }, [load]);

  // Ancho útil del lienzo: la pantalla menos el padding lateral.
  const stageWidth = Math.max(240, Math.min(windowWidth, 900) - 32);
  const baseScale = canvas ? stageWidth / canvas.width : 1;
  const scale = baseScale * zoom;
  const selected = useMemo(
    () => (canvas?.fields || []).find(f => f.id === selectedId) || null,
    [canvas, selectedId],
  );

  // El input arranca con el texto del recuadro elegido; si agregamos `text` a
  // las dependencias el input se resetea con cada tecla.
  const selectedText = selected?.text ?? '';
  useEffect(() => { setDraftText(selectedText); }, [selected?.id]);  // eslint-disable-line react-hooks/exhaustive-deps

  const patchField = (id: string, patch: Partial<Field>) => {
    setCanvas(prev => prev
      ? { ...prev, fields: prev.fields.map(f => (f.id === id ? { ...f, ...patch } : f)) }
      : prev);
    setDirty(true);
  };

  const removeField = (id: string) => {
    setCanvas(prev => prev ? { ...prev, fields: prev.fields.filter(f => f.id !== id) } : prev);
    setSelectedId(null);
    setDirty(true);
  };

  const askPermission = async () => {
    if (Platform.OS === 'web') return true;
    const current = await ImagePicker.getMediaLibraryPermissionsAsync();
    let { status, canAskAgain } = current;
    if (status !== 'granted' && canAskAgain) {
      const asked = await ImagePicker.requestMediaLibraryPermissionsAsync();
      status = asked.status; canAskAgain = asked.canAskAgain;
    }
    if (status !== 'granted') {
      setDialog({
        title: 'Permiso necesario',
        message: 'Necesitamos ver tus archivos para leer tu menú diseñado.',
        icon: 'images-outline',
        options: canAskAgain
          ? [{ label: 'Entendido', primary: true }]
          : [{ label: 'Abrir Ajustes', primary: true, onPress: () => Linking.openSettings() },
             { label: 'Cancelar' }],
      });
      return false;
    }
    return true;
  };

  /** Sube el diseño (imagen o PDF) y deja que la IA lo vuelva editable. */
  const importDesign = useCallback(async () => {
    if (!(await askPermission())) return;
    const picked = await DocumentPicker.getDocumentAsync({
      type: ['image/jpeg', 'image/png', 'image/webp', 'application/pdf'],
      copyToCacheDirectory: true,
      multiple: false,
    });
    if (picked.canceled || !picked.assets?.length) return;
    const asset = picked.assets[0];
    if (asset.size && asset.size > MAX_BYTES) {
      setDialog({ title: 'Archivo muy grande', message: 'Usá un archivo de menos de 20 MB.' });
      return;
    }
    setImporting(true);
    try {
      const base64 = await FileSystem.readAsStringAsync(asset.uri, { encoding: 'base64' });
      const res = await workspaceAPI.importCanvas(menuId, {
        file_base64: base64,
        content_type: asset.mimeType || 'image/jpeg',
      });
      setCanvas(res.data.canvas);
      setDirty(false);
      setSelectedId(null);
      setDialog({
        title: res.data.detected ? '¡Tu diseño ya es editable!' : 'No encontramos textos',
        icon: res.data.detected ? 'sparkles-outline' : 'alert-circle-outline',
        message: res.data.detected
          ? `Marcamos ${res.data.detected} recuadro(s). Tocá cualquiera para cambiar el texto o la foto.`
          : 'Probá con una imagen más nítida y de frente, o subí el PDF original.',
      });
    } catch (e: any) {
      setDialog({
        title: 'No pudimos procesar tu diseño',
        message: e.response?.data?.detail || e.message || 'Intentá de nuevo en un momento.',
      });
    } finally { setImporting(false); }
  }, [menuId]);

  /** Reemplaza la foto de un recuadro; el backend la recorta al hueco exacto. */
  const replacePhoto = useCallback(async (field: Field) => {
    if (!(await askPermission())) return;
    const res = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'], base64: true, quality: 0.9, allowsMultipleSelection: false,
    });
    if (res.canceled || !res.assets?.length) return;
    const asset = res.assets[0];
    if (!asset.base64) {
      setDialog({ title: 'No pudimos leer la foto', message: 'Elegila de nuevo.' });
      return;
    }
    setPhotoBusy(true);
    try {
      const out = await workspaceAPI.replaceCanvasPhoto(menuId, field.id, {
        image_base64: asset.base64,
        content_type: asset.mimeType || 'image/jpeg',
      });
      patchField(field.id, { image_url: out.data.image_url, media_id: out.data.media_id });
      setDirty(false);
    } catch (e: any) {
      setDialog({
        title: 'No se pudo cambiar la foto',
        message: e.response?.data?.detail || e.message || 'Intentá con otra imagen.',
      });
    } finally { setPhotoBusy(false); }
  }, [menuId]);

  const save = useCallback(async () => {
    if (!canvas) return;
    setSaving(true);
    try {
      await workspaceAPI.saveCanvas(menuId, canvas.fields);
      setDirty(false);
      setDialog({
        title: 'Guardado',
        icon: 'checkmark-circle-outline',
        message: 'Tus cambios ya están listos. Publicá el menú para que lleguen al TV.',
        options: [{ label: 'Publicar ahora', primary: true,
                    onPress: () => router.push(`/workspace/menu-edit?id=${menuId}`) },
                  { label: 'Seguir editando' }],
      });
    } catch (e: any) {
      setDialog({ title: 'No se pudo guardar', message: e.response?.data?.detail || e.message });
    } finally { setSaving(false); }
  }, [canvas, menuId]);

  const preview = useCallback(async () => {
    try {
      const res = await workspaceAPI.menuPreviewUrl(menuId);
      await Linking.openURL(`${API_URL}${res.data.url}`);
    } catch (e: any) {
      setDialog({ title: 'No se pudo abrir la vista previa', message: e.response?.data?.detail || e.message });
    }
  }, [menuId]);

  const dropDesign = () => setDialog({
    title: '¿Quitar tu diseño?',
    message: 'El menú vuelve a mostrarse con la plantilla de MediaView.',
    icon: 'trash-outline',
    options: [
      { label: 'Quitar diseño', destructive: true, onPress: async () => {
        try { await workspaceAPI.deleteCanvas(menuId); setCanvas(null); }
        catch (e: any) { setDialog({ title: 'No se pudo quitar', message: e.response?.data?.detail || e.message }); }
      }},
      { label: 'Cancelar' },
    ],
  });

  if (loading) {
    return (
      <View style={[st.root, st.center]}>
        <ActivityIndicator color="#0891B2" size="large" />
      </View>
    );
  }

  return (
    <View style={st.root}>
      <View style={[st.topBar, { paddingTop: insets.top + 8 }]}>
        <TouchableOpacity style={st.backBtn} onPress={() => router.back()} hitSlop={10}>
          <Ionicons name="arrow-back" size={20} color="#64748B" />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={st.topTitle} numberOfLines={1}>{menuName || 'Mi diseño'}</Text>
          <Text style={st.topSub}>Mi propio diseño</Text>
        </View>
        {!!canvas && (
          <TouchableOpacity style={st.iconBtn} onPress={preview} hitSlop={8} testID="canvas-preview">
            <Ionicons name="tv-outline" size={20} color="#0E7490" />
          </TouchableOpacity>
        )}
        {!!canvas && (
          <TouchableOpacity
            style={[st.saveBtn, (!dirty || saving) && { opacity: 0.45 }]}
            onPress={save}
            disabled={!dirty || saving}
            testID="canvas-save"
          >
            {saving ? <ActivityIndicator size={14} color="#fff" />
                    : <Text style={st.saveBtnText}>Guardar</Text>}
          </TouchableOpacity>
        )}
      </View>

      {!canvas ? (
        <ScrollView contentContainerStyle={st.emptyWrap}>
          <View style={st.emptyIcon}>
            <Ionicons name="color-palette-outline" size={34} color="#0891B2" />
          </View>
          <Text style={st.emptyTitle}>Usá tu menú como está</Text>
          <Text style={st.emptyText}>
            Subí el menú que ya tenés diseñado en JPG, PNG o PDF. La IA encuentra los nombres,
            los precios y las fotos, y te deja cambiarlos sin tocar tu diseño: mismos colores,
            misma tipografía, mismo lugar.
          </Text>
          <TouchableOpacity
            style={[st.primaryBtn, importing && { opacity: 0.6 }]}
            onPress={importDesign}
            disabled={importing}
            testID="canvas-upload"
          >
            {importing
              ? <><ActivityIndicator size={16} color="#fff" />
                  <Text style={st.primaryBtnText}>Analizando tu diseño…</Text></>
              : <><Ionicons name="cloud-upload-outline" size={18} color="#fff" />
                  <Text style={st.primaryBtnText}>Subir mi menú</Text></>}
          </TouchableOpacity>
          <Text style={st.emptyHint}>Hasta 20 MB · del PDF usamos la primera página</Text>
        </ScrollView>
      ) : (
        <>
          <View style={st.toolbar}>
            <Text style={st.toolbarText}>
              {canvas.fields.length} recuadro{canvas.fields.length === 1 ? '' : 's'} · tocá para editar
            </Text>
            <View style={st.zoomRow}>
              {[1, 2, 3].map(level => (
                <TouchableOpacity
                  key={level}
                  style={[st.zoomBtn, zoom === level && st.zoomBtnOn]}
                  onPress={() => setZoom(level)}
                  testID={`zoom-${level}`}
                >
                  <Text style={[st.zoomText, zoom === level && st.zoomTextOn]}>{level}x</Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>

          <ScrollView style={st.stageScrollV} contentContainerStyle={{ paddingBottom: insets.bottom + 260 }}>
            <ScrollView horizontal showsHorizontalScrollIndicator contentContainerStyle={st.stagePad}>
              <View
                style={{
                  width: canvas.width * scale,
                  height: canvas.height * scale,
                  backgroundColor: '#F1F5F9',
                }}
              >
                <Image
                  source={{ uri: `${API_URL}${canvas.background_url}` }}
                  style={{ width: canvas.width * scale, height: canvas.height * scale }}
                  resizeMode="contain"
                />
                {canvas.fields.map(field => (
                  <FieldBox
                    key={field.id}
                    field={field}
                    scale={scale}
                    selected={field.id === selectedId}
                    onSelect={() => setSelectedId(field.id)}
                    onGeometry={patch => patchField(field.id, patch)}
                  />
                ))}
              </View>
            </ScrollView>

            <TouchableOpacity style={st.dropBtn} onPress={dropDesign}>
              <Ionicons name="trash-outline" size={15} color="#DC2626" />
              <Text style={st.dropBtnText}>Quitar mi diseño y volver a la plantilla</Text>
            </TouchableOpacity>
          </ScrollView>
        </>
      )}

      {/* Editor del recuadro seleccionado */}
      <Modal visible={!!selected} transparent animationType="slide"
             onRequestClose={() => setSelectedId(null)}>
        <View style={st.sheetOverlay}>
          <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
            <View style={[st.sheet, { paddingBottom: insets.bottom + 20 }]}>
              <View style={st.sheetHeader}>
                <View style={[st.kindChip, { backgroundColor: `${KIND_COLOR[selected?.kind || 'name']}1A` }]}>
                  <Text style={[st.kindChipText, { color: KIND_COLOR[selected?.kind || 'name'] }]}>
                    {KIND_LABEL[selected?.kind || 'name']}
                  </Text>
                </View>
                <TouchableOpacity onPress={() => setSelectedId(null)} hitSlop={12}>
                  <Ionicons name="close" size={22} color="#64748B" />
                </TouchableOpacity>
              </View>

              {selected?.kind === 'photo' ? (
                <>
                  {selected.image_url ? (
                    <Image source={{ uri: `${API_URL}${selected.image_url}` }}
                           style={st.photoPreview} resizeMode="cover" />
                  ) : (
                    <View style={[st.photoPreview, st.center]}>
                      <Ionicons name="image-outline" size={26} color="#94A3B8" />
                      <Text style={st.photoHint}>Se ve la foto original de tu diseño</Text>
                    </View>
                  )}
                  <TouchableOpacity
                    style={[st.primaryBtn, photoBusy && { opacity: 0.6 }]}
                    onPress={() => selected && replacePhoto(selected)}
                    disabled={photoBusy}
                    testID="replace-photo"
                  >
                    {photoBusy
                      ? <><ActivityIndicator size={16} color="#fff" />
                          <Text style={st.primaryBtnText}>Ajustando al recuadro…</Text></>
                      : <><Ionicons name="camera-outline" size={18} color="#fff" />
                          <Text style={st.primaryBtnText}>
                            {selected.image_url ? 'Cambiar foto' : 'Poner mi foto'}
                          </Text></>}
                  </TouchableOpacity>
                  {!!selected.image_url && (
                    <TouchableOpacity
                      style={st.ghostBtn}
                      onPress={() => patchField(selected.id, { image_url: null, media_id: null })}
                    >
                      <Text style={st.ghostBtnText}>Volver a la foto original</Text>
                    </TouchableOpacity>
                  )}
                  <Text style={st.sheetHint}>
                    Tu foto se recorta sola al tamaño y al borde que ya tiene el diseño.
                  </Text>
                </>
              ) : (
                <>
                  <Text style={st.fieldLabel}>
                    {selected?.kind === 'price' ? 'Precio' : 'Texto'}
                  </Text>
                  <TextInput
                    style={st.input}
                    value={draftText}
                    onChangeText={setDraftText}
                    onBlur={() => selected && patchField(selected.id, { text: draftText })}
                    placeholder={selected?.original_text || 'Escribí acá'}
                    placeholderTextColor="#CBD5E1"
                    autoCapitalize="none"
                    testID="field-text"
                  />
                  <View style={st.alignRow}>
                    {(['left', 'center', 'right'] as const).map(option => (
                      <TouchableOpacity
                        key={option}
                        style={[st.alignBtn, selected?.align === option && st.alignBtnOn]}
                        onPress={() => selected && patchField(selected.id, { align: option })}
                      >
                        <Ionicons
                          name={`text-outline`}
                          size={14}
                          color={selected?.align === option ? '#0E7490' : '#94A3B8'}
                        />
                        <Text style={[st.alignText, selected?.align === option && st.alignTextOn]}>
                          {option === 'left' ? 'Izq.' : option === 'center' ? 'Centro' : 'Der.'}
                        </Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                  {!!selected?.original_text && (
                    <Text style={st.sheetHint}>
                      Original: «{selected.original_text}». Si lo dejás igual, el TV muestra el
                      diseño sin tocar.
                    </Text>
                  )}
                  <TouchableOpacity
                    style={st.applyBtn}
                    onPress={() => { selected && patchField(selected.id, { text: draftText }); setSelectedId(null); }}
                    testID="field-apply"
                  >
                    <Text style={st.applyBtnText}>Listo</Text>
                  </TouchableOpacity>
                </>
              )}

              <TouchableOpacity style={st.deleteBtn} onPress={() => selected && removeField(selected.id)}>
                <Ionicons name="trash-outline" size={15} color="#DC2626" />
                <Text style={st.deleteBtnText}>Eliminar recuadro</Text>
              </TouchableOpacity>
            </View>
          </KeyboardAvoidingView>
        </View>
      </Modal>

      <AppDialog state={dialog} onDismiss={() => setDialog(null)} />
    </View>
  );
}

const st = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#F8FAFC' },
  center: { justifyContent: 'center', alignItems: 'center' },
  topBar: {
    flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 16, paddingBottom: 12,
    backgroundColor: '#FFFFFF', borderBottomWidth: 1, borderBottomColor: '#E2E8F0',
  },
  backBtn: { width: 36, height: 36, borderRadius: 10, justifyContent: 'center', alignItems: 'center', backgroundColor: '#F1F5F9' },
  topTitle: { fontSize: 16, fontWeight: '800', color: '#0F172A' },
  topSub: { fontSize: 11, color: '#64748B', fontWeight: '600' },
  iconBtn: { width: 40, height: 40, borderRadius: 10, justifyContent: 'center', alignItems: 'center', backgroundColor: '#ECFEFF' },
  saveBtn: { backgroundColor: '#0891B2', paddingHorizontal: 16, minHeight: 40, borderRadius: 10, justifyContent: 'center', alignItems: 'center' },
  saveBtnText: { color: '#fff', fontSize: 13, fontWeight: '700' },

  emptyWrap: { padding: 24, alignItems: 'center', gap: 12 },
  emptyIcon: { width: 68, height: 68, borderRadius: 20, backgroundColor: '#ECFEFF', justifyContent: 'center', alignItems: 'center', marginTop: 28 },
  emptyTitle: { fontSize: 19, fontWeight: '800', color: '#0F172A', marginTop: 4 },
  emptyText: { fontSize: 14, color: '#475569', textAlign: 'center', lineHeight: 21 },
  emptyHint: { fontSize: 11, color: '#94A3B8' },

  toolbar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 16, paddingVertical: 10 },
  toolbarText: { fontSize: 12, color: '#64748B', fontWeight: '600', flex: 1 },
  zoomRow: { flexDirection: 'row', gap: 6 },
  zoomBtn: { minWidth: 44, minHeight: 32, paddingHorizontal: 10, borderRadius: 9, backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#E2E8F0', justifyContent: 'center', alignItems: 'center' },
  zoomBtnOn: { backgroundColor: '#ECFEFF', borderColor: '#0891B2' },
  zoomText: { fontSize: 12, fontWeight: '700', color: '#64748B' },
  zoomTextOn: { color: '#0E7490' },

  stageScrollV: { flex: 1 },
  stagePad: { paddingHorizontal: 16, paddingBottom: 16 },
  box: { position: 'absolute', borderRadius: 3 },
  handle: { position: 'absolute', right: -9, bottom: -9, width: 20, height: 20, borderRadius: 10, justifyContent: 'center', alignItems: 'center' },

  dropBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, marginTop: 18, paddingVertical: 12 },
  dropBtnText: { fontSize: 12, color: '#DC2626', fontWeight: '600' },

  sheetOverlay: { flex: 1, justifyContent: 'flex-end', backgroundColor: 'rgba(15,23,42,0.45)' },
  sheet: { backgroundColor: '#FFFFFF', borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: 20, gap: 12 },
  sheetHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  kindChip: { paddingHorizontal: 10, paddingVertical: 5, borderRadius: 8 },
  kindChipText: { fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.5 },
  sheetHint: { fontSize: 11, color: '#64748B', lineHeight: 16 },
  fieldLabel: { fontSize: 11, fontWeight: '700', color: '#64748B', textTransform: 'uppercase', letterSpacing: 0.4 },
  input: { fontSize: 16, color: '#0F172A', backgroundColor: '#F8FAFC', borderWidth: 1, borderColor: '#E2E8F0', borderRadius: 10, padding: 14, minHeight: 48 },
  alignRow: { flexDirection: 'row', gap: 8 },
  alignBtn: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 5, minHeight: 44, borderRadius: 10, borderWidth: 1, borderColor: '#E2E8F0', backgroundColor: '#F8FAFC' },
  alignBtnOn: { borderColor: '#0891B2', backgroundColor: '#ECFEFF' },
  alignText: { fontSize: 12, fontWeight: '600', color: '#94A3B8' },
  alignTextOn: { color: '#0E7490' },
  applyBtn: { backgroundColor: '#0891B2', minHeight: 48, borderRadius: 12, justifyContent: 'center', alignItems: 'center' },
  applyBtnText: { color: '#fff', fontSize: 15, fontWeight: '700' },

  photoPreview: { width: '100%', height: 150, borderRadius: 12, backgroundColor: '#F1F5F9', gap: 6 },
  photoHint: { fontSize: 11, color: '#94A3B8' },
  primaryBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: '#0891B2', minHeight: 50, paddingHorizontal: 20, borderRadius: 12, marginTop: 8 },
  primaryBtnText: { color: '#fff', fontSize: 15, fontWeight: '700' },
  ghostBtn: { minHeight: 44, justifyContent: 'center', alignItems: 'center' },
  ghostBtnText: { fontSize: 13, color: '#0E7490', fontWeight: '600' },
  deleteBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, minHeight: 44 },
  deleteBtnText: { fontSize: 13, color: '#DC2626', fontWeight: '600' },
});
