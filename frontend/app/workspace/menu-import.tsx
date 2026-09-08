import React, { useState, useCallback } from 'react';
import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity, TextInput, Image,
  ActivityIndicator, Platform, Linking,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import * as ImagePicker from 'expo-image-picker';
import { workspaceAPI } from '../../src/services/api';
import AppDialog, { type DialogState } from '../../src/components/AppDialog';

type Draft = { key: string; name: string; price: string; category?: string | null; description?: string | null };

const MAX_BYTES = 10 * 1024 * 1024;

export default function MenuImport() {
  const insets = useSafeAreaInsets();
  const [photo, setPhoto] = useState<string | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [menuName, setMenuName] = useState('');
  const [items, setItems] = useState<Draft[] | null>(null);
  const [creating, setCreating] = useState(false);
  const [dialog, setDialog] = useState<DialogState>(null);

  const pickPhoto = useCallback(async () => {
    if (Platform.OS !== 'web') {
      const current = await ImagePicker.getMediaLibraryPermissionsAsync();
      let status = current.status;
      let canAskAgain = current.canAskAgain;
      if (status !== 'granted' && canAskAgain) {
        const asked = await ImagePicker.requestMediaLibraryPermissionsAsync();
        status = asked.status; canAskAgain = asked.canAskAgain;
      }
      if (status !== 'granted') {
        setDialog({
          title: 'Permiso necesario',
          message: 'Necesitamos ver tus fotos para leer la imagen de tu menú.',
          icon: 'images-outline',
          options: canAskAgain
            ? [{ label: 'Entendido', primary: true }]
            : [{ label: 'Abrir Ajustes', primary: true, onPress: () => Linking.openSettings() },
               { label: 'Cancelar' }],
        });
        return;
      }
    }

    const res = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'], base64: true, quality: 0.85, allowsMultipleSelection: false,
    });
    if (res.canceled || !res.assets?.length) return;
    const asset = res.assets[0];
    if (!asset.base64) {
      setDialog({ title: 'No pudimos leer la foto', message: 'Intenta elegirla de nuevo.' });
      return;
    }
    if (asset.fileSize && asset.fileSize > MAX_BYTES) {
      setDialog({ title: 'Foto muy grande', message: 'Usa una imagen de menos de 10 MB.' });
      return;
    }

    setPhoto(asset.uri);
    setItems(null);
    setAnalyzing(true);
    try {
      const out = await workspaceAPI.aiImportMenu({
        image_base64: asset.base64,
        content_type: asset.mimeType || 'image/jpeg',
      });
      const extracted: Draft[] = (out.data.items || []).map((it: any, i: number) => ({
        key: `ai-${i}`,
        name: it.name || '',
        price: String(it.price ?? 0),
        category: it.category,
        description: it.description,
      }));
      setMenuName(out.data.menu_name || 'Menú');
      setItems(extracted);
      if (extracted.length === 0) {
        setDialog({
          title: 'No encontramos productos',
          message: 'Asegúrate de que la foto sea del menú, con buena luz y de frente.',
        });
      }
    } catch (e: any) {
      setDialog({
        title: 'La IA no pudo leer el menú',
        message: e.response?.data?.detail || e.message || 'Intenta de nuevo con otra foto.',
      });
    } finally { setAnalyzing(false); }
  }, []);

  const updateItem = (key: string, field: 'name' | 'price', value: string) =>
    setItems(prev => (prev || []).map(it => it.key === key
      ? { ...it, [field]: field === 'price' ? value.replace(/[^\d.]/g, '').slice(0, 8) : value }
      : it));

  const removeItem = (key: string) => setItems(prev => (prev || []).filter(it => it.key !== key));

  const createMenu = useCallback(async () => {
    const valid = (items || []).filter(it => it.name.trim());
    if (!menuName.trim()) { setDialog({ title: 'Ponle un nombre al menú' }); return; }
    if (valid.length === 0) { setDialog({ title: 'Agrega al menos un producto' }); return; }
    setCreating(true);
    try {
      const res = await workspaceAPI.createMenu({
        name: menuName.trim(),
        source: 'ai_photo',
        items: valid.map(it => ({
          name: it.name.trim(),
          price: Number(it.price) || 0,
          category: it.category || undefined,
          description: it.description || undefined,
          available: true,
        })),
      });
      router.replace({ pathname: '/workspace/menu-edit', params: { id: res.data.id } });
    } catch (e: any) {
      setDialog({ title: 'No se pudo crear el menú', message: e.response?.data?.detail || e.message });
    } finally { setCreating(false); }
  }, [items, menuName]);

  return (
    <View style={mi.root}>
      <ScrollView contentContainerStyle={[mi.content, { paddingBottom: insets.bottom + 32 }]} keyboardShouldPersistTaps="handled">
        <View style={mi.header}>
          <TouchableOpacity onPress={() => router.push('/workspace/menus')} style={mi.backBtn} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
            <Ionicons name="arrow-back" size={20} color="#64748B" />
          </TouchableOpacity>
          <View style={{ flex: 1 }}>
            <Text style={mi.title}>Importar Menú con IA</Text>
            <Text style={mi.sub}>Sube la foto de tu menú y la IA escribe los productos y precios</Text>
          </View>
        </View>

        {!photo && (
          <TouchableOpacity style={mi.dropZone} onPress={pickPhoto} activeOpacity={0.85}>
            <View style={mi.dropIcon}><Ionicons name="camera-outline" size={30} color="#0891B2" /></View>
            <Text style={mi.dropTitle}>Elegir foto del menú</Text>
            <Text style={mi.dropText}>JPG, PNG o WebP hasta 10 MB. Toma la foto de frente y con buena luz.</Text>
          </TouchableOpacity>
        )}

        {!!photo && (
          <View style={mi.previewCard}>
            <Image source={{ uri: photo }} style={mi.preview} resizeMode="cover" />
            <TouchableOpacity style={mi.changeBtn} onPress={pickPhoto} activeOpacity={0.8}>
              <Ionicons name="refresh" size={15} color="#0891B2" />
              <Text style={mi.changeText}>Cambiar foto</Text>
            </TouchableOpacity>
          </View>
        )}

        {analyzing && (
          <View style={mi.analyzing}>
            <ActivityIndicator color="#0891B2" />
            <Text style={mi.analyzingText}>Leyendo tu menú… esto puede tardar hasta 30 segundos.</Text>
          </View>
        )}

        {!!items && !analyzing && (
          <>
            <Text style={mi.label}>Nombre del menú</Text>
            <TextInput
              style={mi.input}
              value={menuName}
              onChangeText={setMenuName}
              placeholder="ej. Menú Principal"
              placeholderTextColor="#CBD5E1"
            />

            <View style={mi.reviewHeader}>
              <Text style={mi.label}>Productos encontrados ({items.length})</Text>
              <Text style={mi.reviewHint}>Revisa y corrige antes de crear</Text>
            </View>

            {items.map(it => (
              <View key={it.key} style={mi.itemRow}>
                <View style={{ flex: 1, gap: 6 }}>
                  <TextInput
                    style={mi.itemName}
                    value={it.name}
                    onChangeText={(t) => updateItem(it.key, 'name', t)}
                    placeholder="Nombre del producto"
                    placeholderTextColor="#CBD5E1"
                  />
                  {!!it.category && <Text style={mi.itemCat}>{it.category}</Text>}
                </View>
                <View style={mi.priceBox}>
                  <Text style={mi.currency}>$</Text>
                  <TextInput
                    style={mi.priceInput}
                    value={it.price}
                    onChangeText={(t) => updateItem(it.key, 'price', t)}
                    keyboardType="decimal-pad"
                    placeholder="0.00"
                    placeholderTextColor="#CBD5E1"
                  />
                </View>
                <TouchableOpacity onPress={() => removeItem(it.key)} style={mi.removeBtn} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
                  <Ionicons name="close" size={18} color="#DC2626" />
                </TouchableOpacity>
              </View>
            ))}

            <TouchableOpacity
              style={[mi.createBtn, creating && { opacity: 0.6 }]}
              onPress={createMenu}
              disabled={creating}
              activeOpacity={0.85}
            >
              {creating ? <ActivityIndicator color="#fff" /> : <Text style={mi.createText}>Crear Menú con {items.length} productos</Text>}
            </TouchableOpacity>
          </>
        )}
      </ScrollView>

      <AppDialog state={dialog} onDismiss={() => setDialog(null)} />
    </View>
  );
}

const mi = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#F8FAFC' },
  content: { padding: 20 },
  header: { flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 20 },
  backBtn: { width: 40, height: 40, borderRadius: 12, backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#E2E8F0', alignItems: 'center', justifyContent: 'center' },
  title: { fontSize: 20, fontWeight: '800', color: '#0F172A' },
  sub: { fontSize: 12.5, color: '#64748B', marginTop: 2, lineHeight: 17 },
  dropZone: {
    alignItems: 'center', gap: 8, backgroundColor: '#FFFFFF', borderWidth: 2,
    borderStyle: 'dashed', borderColor: '#CFFAFE', borderRadius: 18, padding: 32,
  },
  dropIcon: { width: 64, height: 64, borderRadius: 18, backgroundColor: '#ECFEFF', alignItems: 'center', justifyContent: 'center', marginBottom: 6 },
  dropTitle: { fontSize: 16, fontWeight: '800', color: '#0F172A' },
  dropText: { fontSize: 12.5, color: '#64748B', textAlign: 'center', lineHeight: 18, maxWidth: 300 },
  previewCard: { backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#E2E8F0', borderRadius: 16, padding: 12, gap: 10 },
  preview: { width: '100%', height: 220, borderRadius: 12, backgroundColor: '#E2E8F0' },
  changeBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 10, minHeight: 44 },
  changeText: { fontSize: 13, color: '#0891B2', fontWeight: '700' },
  analyzing: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: '#ECFEFF', borderWidth: 1, borderColor: '#CFFAFE', borderRadius: 12, padding: 16, marginTop: 14 },
  analyzingText: { fontSize: 13, color: '#0E7490', fontWeight: '600', flex: 1 },
  label: { fontSize: 11, fontWeight: '700', color: '#64748B', letterSpacing: 0.6, textTransform: 'uppercase', marginTop: 20, marginBottom: 8 },
  input: {
    fontSize: 15, color: '#0F172A', backgroundColor: '#FFFFFF', borderWidth: 1,
    borderColor: '#E2E8F0', borderRadius: 12, padding: 14,
    ...(Platform.OS === 'web' ? ({ outlineStyle: 'none' } as any) : null),
  },
  reviewHeader: { flexDirection: 'row', alignItems: 'flex-end', justifyContent: 'space-between' },
  reviewHint: { fontSize: 11.5, color: '#94A3B8', marginBottom: 8 },
  itemRow: {
    flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: '#FFFFFF',
    borderWidth: 1, borderColor: '#E2E8F0', borderRadius: 12, padding: 12, marginBottom: 8,
  },
  itemName: {
    fontSize: 14, fontWeight: '600', color: '#0F172A', padding: 0,
    ...(Platform.OS === 'web' ? ({ outlineStyle: 'none' } as any) : null),
  },
  itemCat: { fontSize: 11, color: '#94A3B8', textTransform: 'uppercase', letterSpacing: 0.4 },
  priceBox: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#F8FAFC', borderWidth: 1, borderColor: '#E2E8F0', borderRadius: 10, paddingHorizontal: 8 },
  currency: { fontSize: 13, color: '#64748B', fontWeight: '700' },
  priceInput: {
    width: 62, fontSize: 14, fontWeight: '700', color: '#0F172A', textAlign: 'center', paddingVertical: 8,
    ...(Platform.OS === 'web' ? ({ outlineStyle: 'none' } as any) : null),
  },
  removeBtn: { width: 34, height: 34, borderRadius: 9, alignItems: 'center', justifyContent: 'center', backgroundColor: '#FEF2F2' },
  createBtn: { backgroundColor: '#0891B2', borderRadius: 14, paddingVertical: 16, alignItems: 'center', marginTop: 18 },
  createText: { color: '#FFFFFF', fontSize: 15, fontWeight: '700' },
});
