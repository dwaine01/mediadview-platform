/**
 * design-edit.tsx — «Elegir → Reemplazar contenido → Vista previa → Publicar».
 *
 * No es un editor gráfico a propósito: la composición profesional de la
 * plantilla queda intacta y el cliente sólo reemplaza contenido. Toca un
 * producto, le cambia el nombre, el precio o la foto, y listo.
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, TextInput, ScrollView, Image, Modal,
  ActivityIndicator, Linking, Platform, KeyboardAvoidingView,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { router, useLocalSearchParams } from 'expo-router';
import * as ImagePicker from 'expo-image-picker';
import { workspaceAPI } from '../../src/services/api';
import AppDialog, { type DialogState } from '../../src/components/AppDialog';

const API_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';

type Product = {
  id: string; name: string; description?: string; price?: number | string;
  sale_price?: number | string | null; image_url?: string;
  variants?: { label: string; price: number | string }[];
  available?: boolean; featured?: boolean;
};

export default function DesignEdit() {
  const insets = useSafeAreaInsets();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [design, setDesign] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState<Product | null>(null);
  const [draft, setDraft] = useState<Product | null>(null);
  const [photoBusy, setPhotoBusy] = useState(false);
  const [screens, setScreens] = useState<any[]>([]);
  const [picked, setPicked] = useState<string[]>([]);
  const [showPublish, setShowPublish] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [dialog, setDialog] = useState<DialogState>(null);

  const load = useCallback(async () => {
    try {
      const res = await workspaceAPI.getDesign(id);
      setDesign(res.data.design);
      setPicked(res.data.design.screen_ids || []);
    } catch (e: any) {
      setDialog({ title: 'No pudimos abrir el diseño',
                  message: e.response?.data?.detail || e.message });
    } finally { setLoading(false); }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  const products: Record<string, Product> = design?.products || {};
  const categories = design?.bindings?.categories || [];

  const saveProduct = async () => {
    if (!draft) return;
    setSaving(true);
    try {
      const res = await workspaceAPI.updateDesignProduct(id, draft.id, {
        name: draft.name, description: draft.description,
        price: draft.price, variants: draft.variants, available: draft.available,
      });
      setDesign((prev: any) => ({ ...prev, products: { ...prev.products, [draft.id]: res.data } }));
      setEditing(null);
    } catch (e: any) {
      setDialog({ title: 'No se pudo guardar', message: e.response?.data?.detail || e.message });
    } finally { setSaving(false); }
  };

  const replacePhoto = async () => {
    if (!draft) return;
    if (Platform.OS !== 'web') {
      const current = await ImagePicker.getMediaLibraryPermissionsAsync();
      let { status, canAskAgain } = current;
      if (status !== 'granted' && canAskAgain) {
        const asked = await ImagePicker.requestMediaLibraryPermissionsAsync();
        status = asked.status; canAskAgain = asked.canAskAgain;
      }
      if (status !== 'granted') {
        setDialog({
          title: 'Permiso necesario',
          message: 'Necesitamos ver tus fotos para poner la de tu producto.',
          icon: 'images-outline',
          options: canAskAgain ? [{ label: 'Entendido', primary: true }]
            : [{ label: 'Abrir Ajustes', primary: true, onPress: () => Linking.openSettings() },
               { label: 'Cancelar' }],
        });
        return;
      }
    }
    const res = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'], base64: true, quality: 0.9,
    });
    if (res.canceled || !res.assets?.[0]?.base64) return;
    setPhotoBusy(true);
    try {
      const out = await workspaceAPI.uploadDesignPhoto(id, draft.id, {
        image_base64: res.assets[0].base64!,
        content_type: res.assets[0].mimeType || 'image/jpeg',
      });
      setDraft(out.data);
      setDesign((prev: any) => ({ ...prev, products: { ...prev.products, [draft.id]: out.data } }));
    } catch (e: any) {
      setDialog({ title: 'No se pudo cambiar la foto',
                  message: e.response?.data?.detail || e.message });
    } finally { setPhotoBusy(false); }
  };

  const preview = () => Linking.openURL(`${API_URL}/api/designs/${id}/render?t=${Date.now()}`);

  const openPublish = async () => {
    try {
      const res = await workspaceAPI.screens();
      setScreens(res.data || []);
      setShowPublish(true);
    } catch (e: any) {
      setDialog({ title: 'No pudimos cargar tus pantallas',
                  message: e.response?.data?.detail || e.message });
    }
  };

  const confirmPublish = async () => {
    if (!picked.length) return;
    setPublishing(true);
    try {
      await workspaceAPI.publishDesign(id, picked);
      setShowPublish(false);
      const checks = await Promise.all(picked.slice(0, 4).map(sid =>
        workspaceAPI.screenNowPlaying(sid)
          .then(r => `• ${r.data.screen?.name}: ${r.data.verdict}`).catch(() => null)));
      setDialog({
        title: '¡Publicado!',
        icon: 'checkmark-circle-outline',
        message: `Tu diseño ya está en vivo en ${picked.length} pantalla${picked.length === 1 ? '' : 's'}.`
          + (checks.filter(Boolean).length ? `\n\n${checks.filter(Boolean).join('\n')}` : ''),
      });
      load();
    } catch (e: any) {
      setDialog({ title: 'No se pudo publicar', message: e.response?.data?.detail || e.message });
    } finally { setPublishing(false); }
  };

  if (loading) {
    return <View style={[st.root, st.center]}><ActivityIndicator size="large" color="#7C3AED" /></View>;
  }

  return (
    <View style={st.root}>
      <View style={[st.topBar, { paddingTop: insets.top + 8 }]}>
        <TouchableOpacity style={st.backBtn} onPress={() => router.back()} hitSlop={10}>
          <Ionicons name="arrow-back" size={20} color="#64748B" />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={st.topTitle} numberOfLines={1}>{design?.name}</Text>
          <Text style={st.topSub}>Plantilla profesional</Text>
        </View>
        <TouchableOpacity style={st.iconBtn} onPress={preview} testID="design-preview">
          <Ionicons name="tv-outline" size={20} color="#6D28D9" />
        </TouchableOpacity>
        <TouchableOpacity style={st.pubBtn} onPress={openPublish} testID="design-publish">
          <Text style={st.pubBtnText}>Publicar</Text>
        </TouchableOpacity>
      </View>

      <ScrollView contentContainerStyle={[st.body, { paddingBottom: insets.bottom + 32 }]}>
        <View style={st.brandCard}>
          <Text style={st.label}>Nombre del negocio</Text>
          <TextInput
            style={st.input}
            value={design?.brand?.business_name || ''}
            onChangeText={text => setDesign((p: any) => ({ ...p, brand: { ...p.brand, business_name: text } }))}
            onBlur={() => workspaceAPI.updateDesign(id, { brand: design.brand }).catch(() => {})}
            placeholder="Mi restaurante"
            placeholderTextColor="#CBD5E1"
            testID="business-name"
          />
        </View>

        {categories.map((category: any, index: number) => (
          <View key={index} style={st.catBlock}>
            <Text style={st.catTitle}>{category.name}</Text>
            {(category.product_ids || []).map((pid: string) => {
              const product = products[pid];
              if (!product) return null;
              const price = product.variants?.length
                ? product.variants.map(v => `${v.label} $${v.price}`).join(' · ')
                : `$${product.sale_price ?? product.price ?? ''}`;
              return (
                <TouchableOpacity
                  key={pid}
                  style={st.row}
                  onPress={() => { setEditing(product); setDraft({ ...product }); }}
                  testID={`product-${pid}`}
                >
                  {product.image_url
                    ? <Image source={{ uri: `${API_URL}${product.image_url}` }} style={st.thumb} />
                    : <View style={[st.thumb, st.center]}>
                        <Ionicons name="image-outline" size={18} color="#94A3B8" />
                      </View>}
                  <View style={{ flex: 1 }}>
                    <Text style={st.rowName} numberOfLines={1}>{product.name}</Text>
                    <Text style={st.rowPrice} numberOfLines={1}>{price}</Text>
                  </View>
                  <Ionicons name="chevron-forward" size={17} color="#CBD5E1" />
                </TouchableOpacity>
              );
            })}
          </View>
        ))}
      </ScrollView>

      {/* Ficha del producto */}
      <Modal visible={!!editing} transparent animationType="slide" onRequestClose={() => setEditing(null)}>
        <View style={st.overlay}>
          <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
            <View style={[st.sheet, { paddingBottom: insets.bottom + 20 }]}>
              <View style={st.sheetHead}>
                <Text style={st.sheetTitle}>Producto</Text>
                <TouchableOpacity onPress={() => setEditing(null)} hitSlop={12}>
                  <Ionicons name="close" size={22} color="#64748B" />
                </TouchableOpacity>
              </View>
              {!!draft?.image_url && (
                <Image source={{ uri: `${API_URL}${draft.image_url}` }} style={st.bigPhoto} />
              )}
              <TouchableOpacity
                style={[st.photoBtn, photoBusy && { opacity: 0.6 }]}
                onPress={replacePhoto}
                disabled={photoBusy}
                testID="design-photo"
              >
                {photoBusy ? <ActivityIndicator size={15} color="#6D28D9" />
                  : <><Ionicons name="camera-outline" size={17} color="#6D28D9" />
                      <Text style={st.photoBtnText}>Poner mi foto</Text></>}
              </TouchableOpacity>
              <Text style={st.label}>Nombre</Text>
              <TextInput
                style={st.input} value={draft?.name || ''}
                onChangeText={text => setDraft(d => d && { ...d, name: text })}
                testID="design-product-name"
              />
              {draft?.variants?.length ? draft.variants.map((variant, index) => (
                <View key={index}>
                  <Text style={st.label}>Precio {variant.label}</Text>
                  <TextInput
                    style={st.input} value={String(variant.price ?? '')} keyboardType="decimal-pad"
                    onChangeText={text => setDraft(d => {
                      if (!d?.variants) return d;
                      const next = [...d.variants];
                      next[index] = { ...next[index], price: text };
                      return { ...d, variants: next };
                    })}
                    testID={`design-variant-${index}`}
                  />
                </View>
              )) : (
                <>
                  <Text style={st.label}>Precio</Text>
                  <TextInput
                    style={st.input} value={String(draft?.price ?? '')} keyboardType="decimal-pad"
                    onChangeText={text => setDraft(d => d && { ...d, price: text })}
                    testID="design-product-price"
                  />
                </>
              )}
              <TouchableOpacity
                style={[st.saveBtn, saving && { opacity: 0.6 }]}
                onPress={saveProduct} disabled={saving}
                testID="design-product-save"
              >
                {saving ? <ActivityIndicator size={15} color="#fff" />
                        : <Text style={st.saveBtnText}>Guardar</Text>}
              </TouchableOpacity>
            </View>
          </KeyboardAvoidingView>
        </View>
      </Modal>

      {/* Publicar en pantallas */}
      <Modal visible={showPublish} transparent animationType="slide" onRequestClose={() => setShowPublish(false)}>
        <View style={st.overlay}>
          <View style={[st.sheet, { paddingBottom: insets.bottom + 20 }]}>
            <View style={st.sheetHead}>
              <Text style={st.sheetTitle}>¿En qué pantallas?</Text>
              <TouchableOpacity onPress={() => setShowPublish(false)} hitSlop={12}>
                <Ionicons name="close" size={22} color="#64748B" />
              </TouchableOpacity>
            </View>
            <ScrollView style={{ maxHeight: 320 }}>
              {screens.map(screen => {
                const on = picked.includes(screen.id);
                return (
                  <TouchableOpacity
                    key={screen.id}
                    style={st.screenRow}
                    onPress={() => setPicked(prev => on ? prev.filter(s => s !== screen.id) : [...prev, screen.id])}
                    testID={`screen-${screen.id}`}
                  >
                    <Ionicons
                      name={on ? 'checkbox' : 'square-outline'}
                      size={22} color={on ? '#7C3AED' : '#CBD5E1'}
                    />
                    <Text style={st.screenName}>{screen.name}</Text>
                  </TouchableOpacity>
                );
              })}
            </ScrollView>
            <TouchableOpacity
              style={[st.saveBtn, (!picked.length || publishing) && { opacity: 0.5 }]}
              onPress={confirmPublish} disabled={!picked.length || publishing}
              testID="confirm-publish-design"
            >
              {publishing ? <ActivityIndicator size={15} color="#fff" />
                          : <Text style={st.saveBtnText}>Publicar ahora</Text>}
            </TouchableOpacity>
          </View>
        </View>
      </Modal>

      <AppDialog state={dialog} onDismiss={() => setDialog(null)} />
    </View>
  );
}

const st = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#F8FAFC' },
  center: { justifyContent: 'center', alignItems: 'center' },
  topBar: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 16, paddingBottom: 12, backgroundColor: '#FFFFFF', borderBottomWidth: 1, borderBottomColor: '#E2E8F0' },
  backBtn: { width: 36, height: 36, borderRadius: 10, justifyContent: 'center', alignItems: 'center', backgroundColor: '#F1F5F9' },
  topTitle: { fontSize: 16, fontWeight: '800', color: '#0F172A' },
  topSub: { fontSize: 11, color: '#64748B', fontWeight: '600' },
  iconBtn: { width: 40, height: 40, borderRadius: 10, justifyContent: 'center', alignItems: 'center', backgroundColor: '#F5F3FF' },
  pubBtn: { backgroundColor: '#7C3AED', paddingHorizontal: 14, minHeight: 40, borderRadius: 10, justifyContent: 'center' },
  pubBtnText: { color: '#fff', fontSize: 13, fontWeight: '700' },

  body: { padding: 16, gap: 16 },
  brandCard: { backgroundColor: '#FFFFFF', borderRadius: 14, borderWidth: 1, borderColor: '#E2E8F0', padding: 14, gap: 6 },
  label: { fontSize: 11, fontWeight: '700', color: '#64748B', textTransform: 'uppercase', letterSpacing: 0.4, marginTop: 8 },
  input: { fontSize: 15, color: '#0F172A', backgroundColor: '#F8FAFC', borderWidth: 1, borderColor: '#E2E8F0', borderRadius: 10, paddingHorizontal: 13, minHeight: 46 },

  catBlock: { backgroundColor: '#FFFFFF', borderRadius: 14, borderWidth: 1, borderColor: '#E2E8F0', overflow: 'hidden' },
  catTitle: { fontSize: 12, fontWeight: '800', color: '#6D28D9', textTransform: 'uppercase', letterSpacing: 0.7, paddingHorizontal: 14, paddingTop: 14, paddingBottom: 6 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 14, paddingVertical: 10, minHeight: 64, borderTopWidth: 1, borderTopColor: '#F1F5F9' },
  thumb: { width: 46, height: 46, borderRadius: 10, backgroundColor: '#F1F5F9' },
  rowName: { fontSize: 15, fontWeight: '700', color: '#0F172A' },
  rowPrice: { fontSize: 12, color: '#64748B', marginTop: 2 },

  overlay: { flex: 1, justifyContent: 'flex-end', backgroundColor: 'rgba(15,23,42,0.45)' },
  sheet: { backgroundColor: '#FFFFFF', borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: 20, gap: 8 },
  sheetHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 },
  sheetTitle: { fontSize: 17, fontWeight: '800', color: '#0F172A' },
  bigPhoto: { width: '100%', height: 150, borderRadius: 12, backgroundColor: '#F1F5F9' },
  photoBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 7, minHeight: 46, borderRadius: 11, backgroundColor: '#F5F3FF', borderWidth: 1, borderColor: '#DDD6FE' },
  photoBtnText: { color: '#6D28D9', fontSize: 13, fontWeight: '700' },
  saveBtn: { backgroundColor: '#7C3AED', minHeight: 48, borderRadius: 12, justifyContent: 'center', alignItems: 'center', marginTop: 14 },
  saveBtnText: { color: '#fff', fontSize: 15, fontWeight: '700' },

  screenRow: { flexDirection: 'row', alignItems: 'center', gap: 12, minHeight: 52 },
  screenName: { fontSize: 15, fontWeight: '600', color: '#0F172A' },
});
