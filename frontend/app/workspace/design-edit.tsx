/**
 * design-edit.tsx — «Elegir → Reemplazar contenido → Vista previa → Publicar».
 *
 * No es un editor gráfico a propósito: la composición profesional de la
 * plantilla queda intacta y el cliente sólo reemplaza contenido. Toca un
 * producto, le cambia el nombre, el precio o la foto, y listo.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, TextInput, ScrollView, Image, Modal,
  ActivityIndicator, Linking, Platform, KeyboardAvoidingView, useWindowDimensions,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { router, useLocalSearchParams } from 'expo-router';
import * as ImagePicker from 'expo-image-picker';
import { workspaceAPI } from '../../src/services/api';
import AppDialog, { type DialogState } from '../../src/components/AppDialog';
import HtmlPreview from '../../src/components/HtmlPreview';
import { readPickedImage } from '../../src/utils/imageUpload';

const API_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';

type Product = {
  id: string; name: string; description?: string; price?: number | string;
  sale_price?: number | string | null; image_url?: string; badge?: string;
  variants?: { label: string; price: number | string }[];
  available?: boolean; featured?: boolean;
};

type Field = {
  path: string; label: string; placeholder?: string;
  kind: 'text' | 'url' | 'image'; removable?: boolean;
};
type EditorSchema = {
  groups: { title: string; fields: Field[] }[];
  categories: { index: number; name_path: string; has_header: boolean;
                product_fields: string[]; slots: number | null }[];
};

/** Lee «bindings.categories[0].name» del diseño. */
function readPath(source: any, path: string): any {
  return path.split('.').reduce((node: any, part: string) => {
    if (node === null || node === undefined) return undefined;
    const indexed = part.match(/^(\w+)\[(\d+)\]$/);
    return indexed ? node[indexed[1]]?.[Number(indexed[2])] : node[part];
  }, source);
}

/** Devuelve una copia del diseño con ese campo cambiado. */
function writePath(source: any, path: string, value: any): any {
  const [head, ...rest] = path.split('.');
  const indexed = head.match(/^(\w+)\[(\d+)\]$/);
  if (indexed) {
    const list = [...(source?.[indexed[1]] || [])];
    const at = Number(indexed[2]);
    list[at] = rest.length
      ? writePath(list[at] || {}, rest.join('.'), value)
      : value;
    return { ...(source || {}), [indexed[1]]: list };
  }
  return {
    ...(source || {}),
    [head]: rest.length ? writePath(source?.[head] || {}, rest.join('.'), value) : value,
  };
}

export default function DesignEdit() {
  const insets = useSafeAreaInsets();
  const { width, height } = useWindowDimensions();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [design, setDesign] = useState<any>(null);
  const [editor, setEditor] = useState<EditorSchema>({ groups: [], categories: [] });
  const [canvas, setCanvas] = useState<{ w: number; h: number }>({ w: 1920, h: 1080 });
  const [html, setHtml] = useState<string | null>(null);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState<Product | null>(null);
  const [draft, setDraft] = useState<Product | null>(null);
  const [photoBusy, setPhotoBusy] = useState(false);
  const [screens, setScreens] = useState<any[]>([]);
  const [picked, setPicked] = useState<string[]>([]);
  const [showPublish, setShowPublish] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [flash, setFlash] = useState('');
  const [dialog, setDialog] = useState<DialogState>(null);
  const live = design?.status === 'published' && (design?.screen_ids || []).length > 0;

  const load = useCallback(async () => {
    try {
      const res = await workspaceAPI.getDesign(id);
      setDesign(res.data.design);
      setEditor(res.data.editor || { groups: [], categories: [] });
      const shape = res.data.template?.canvas;
      if (shape?.w && shape?.h) setCanvas({ w: shape.w, h: shape.h });
      setPicked(res.data.design.screen_ids || []);
    } catch (e: any) {
      setDialog({ title: 'No pudimos abrir el diseño',
                  message: e.response?.data?.detail || e.message });
    } finally { setLoading(false); }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  // Lo que todavía no se guardó: si hay una ficha abierta, la vista previa
  // muestra ESE producto con lo que el dueño está escribiendo.
  const previewPatch = useMemo(
    () => ({
      brand: design?.brand,
      bindings: design?.bindings,
      products: draft ? { [draft.id]: draft } : undefined,
    }),
    [design?.brand, design?.bindings, draft],
  );

  useEffect(() => {
    if (!design) return;
    let cancelled = false;
    setPreviewBusy(true);
    // Medio segundo de pausa: se escribe «12.99» de un tirón, no letra por
    // letra, y el TV no se enteró de nada porque esto no guarda.
    const timer = setTimeout(async () => {
      try {
        const res = await workspaceAPI.previewDesign(id, previewPatch);
        if (!cancelled) setHtml(res.data);
      } catch { /* la vista previa no puede romper la edición */ }
      finally { if (!cancelled) setPreviewBusy(false); }
    }, 500);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [id, design, previewPatch]);

  const products: Record<string, Product> = design?.products || {};

  // ── Campos de texto del diseño (los que la plantilla realmente dibuja) ──
  const setField = (path: string, value: any) =>
    setDesign((prev: any) => writePath(prev, path, value));

  const saveFields = useCallback(async (next?: any) => {
    const source = next || design;
    if (!source) return;
    try {
      await workspaceAPI.updateDesign(id, { brand: source.brand, bindings: source.bindings });
      setFlash(live ? 'Guardado · ya está en el TV' : 'Guardado');
      setTimeout(() => setFlash(''), 2600);
    } catch (e: any) {
      setDialog({ title: 'No se pudo guardar', message: e.response?.data?.detail || e.message });
    }
  }, [design, id, live]);

  const clearField = (field: Field) => {
    const next = writePath(design, field.path, field.kind === 'image' ? null : '');
    setDesign(next);
    saveFields(next);
  };

  const saveProduct = async () => {
    if (!draft) return;
    setSaving(true);
    try {
      const res = await workspaceAPI.updateDesignProduct(id, draft.id, {
        name: draft.name, description: draft.description, badge: draft.badge,
        price: draft.price, variants: draft.variants, available: draft.available,
      });
      setDesign((prev: any) => ({ ...prev, products: { ...prev.products, [draft.id]: res.data } }));
      setEditing(null);
      // Ya está en vivo: el backend sube la versión del playlist al guardar, no
      // hace falta volver a publicar. Se lo decimos, si no el dueño lo duda.
      setFlash(live ? 'Guardado · ya está en el TV' : 'Guardado');
      setTimeout(() => setFlash(''), 2600);
    } catch (e: any) {
      setDialog({ title: 'No se pudo guardar', message: e.response?.data?.detail || e.message });
    } finally { setSaving(false); }
  };

  const addProduct = async (index: number) => {
    try {
      const res = await workspaceAPI.addDesignProduct(id, index);
      await load();
      setEditing(res.data); setDraft(res.data);
    } catch (e: any) {
      setDialog({ title: 'No se pudo agregar', message: e.response?.data?.detail || e.message });
    }
  };

  const removeProduct = (product: Product) => setDialog({
    title: `¿Quitar «${product.name}»?`,
    message: 'Desaparece de la cartelera. Los demás productos se acomodan solos.',
    icon: 'trash-outline',
    options: [
      { label: 'Quitar', destructive: true, onPress: async () => {
        try { setEditing(null); await workspaceAPI.deleteDesignProduct(id, product.id); load(); }
        catch (e: any) { setDialog({ title: 'No se pudo quitar',
                                     message: e.response?.data?.detail || e.message }); }
      }},
      { label: 'Cancelar' },
    ],
  });

  const pickImage = async (): Promise<{ base64: string; mime: string } | null> => {
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
        return null;
      }
    }
    const res = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'], base64: Platform.OS !== 'web', quality: 0.9,
    });
    const asset = res.assets?.[0];
    if (res.canceled || !asset) return null;
    return readPickedImage(asset as any);
  };

  const uploadLogo = async () => {
    setPhotoBusy(true);
    try {
      const picked = await pickImage();
      if (!picked?.base64) return;
      const out = await workspaceAPI.uploadDesignLogo(id, {
        image_base64: picked.base64, content_type: picked.mime,
      });
      setDesign((prev: any) => ({ ...prev, brand: out.data }));
      setFlash(live ? 'Logo cambiado · ya está en el TV' : 'Logo cambiado');
      setTimeout(() => setFlash(''), 2600);
    } catch (e: any) {
      setDialog({ title: 'No se pudo subir el logo',
                  message: e.response?.data?.detail || e.message });
    } finally { setPhotoBusy(false); }
  };

  const replacePhoto = async () => {
    if (!draft) return;
    setPhotoBusy(true);
    try {
      const picked = await pickImage();
      if (!picked?.base64) return;
      const out = await workspaceAPI.uploadDesignPhoto(id, draft.id, {
        image_base64: picked.base64, content_type: picked.mime,
      });
      setDraft(out.data);
      setDesign((prev: any) => ({ ...prev, products: { ...prev.products, [draft.id]: out.data } }));
      setFlash(live ? 'Foto cambiada · ya está en el TV' : 'Foto cambiada');
      setTimeout(() => setFlash(''), 2600);
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

  // Qué campos tiene sentido mostrar de este producto: los que su sección de
  // la plantilla realmente dibuja.
  const section = editor.categories.find(item =>
    (design?.bindings?.categories?.[item.index]?.product_ids || []).includes(editing?.id));
  const shows = (field: string) =>
    (section?.product_fields || ['name', 'price', 'image', 'description', 'badge']).includes(field);

  return (
    <View style={st.root}>
      <View style={[st.topBar, { paddingTop: insets.top + 8 }]}>
        <TouchableOpacity style={st.backBtn} onPress={() => router.back()} hitSlop={10}>
          <Ionicons name="arrow-back" size={20} color="#64748B" />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={st.topTitle} numberOfLines={1}>{design?.name}</Text>
          <Text style={[st.topSub, !!flash && st.topSubOk]} numberOfLines={1}>
            {flash || (live ? 'En vivo · los cambios salen al aire al guardar' : 'Sin publicar')}
          </Text>
        </View>
        <TouchableOpacity style={st.iconBtn} onPress={preview} testID="design-preview">
          <Ionicons name="tv-outline" size={20} color="#6D28D9" />
        </TouchableOpacity>
        <TouchableOpacity style={st.pubBtn} onPress={openPublish} testID="design-publish">
          <Text style={st.pubBtnText}>{live ? 'Pantallas' : 'Publicar'}</Text>
        </TouchableOpacity>
      </View>

      <ScrollView contentContainerStyle={[st.body, { paddingBottom: insets.bottom + 32 }]}>
        {/* Así se ve en el TV, con lo que estoy escribiendo. */}
        <View style={st.previewCard}>
          <View style={st.previewHead}>
            <Text style={st.previewTitle}>Así se ve en el TV</Text>
            <TouchableOpacity onPress={preview} hitSlop={8} testID="design-preview-full">
              <Text style={st.previewLink}>Pantalla completa</Text>
            </TouchableOpacity>
          </View>
          <HtmlPreview
            html={html}
            canvasW={canvas.w}
            canvasH={canvas.h}
            maxWidth={Math.min(width, 900) - 60}
            maxHeight={Math.min(height * 0.42, 420)}
            loading={previewBusy}
            testID="design-live-preview"
          />
        </View>

        {/* Todo lo que la plantilla dibuja tiene su campo acá: los grupos y las
            secciones los declara la propia plantilla, así no queda nada fijo. */}
        {editor.groups.map(group => (
          <View key={group.title} style={st.brandCard}>
            <Text style={st.groupTitle}>{group.title}</Text>
            {group.fields.map(field => field.kind === 'image' ? (
              <View key={field.path} style={st.logoRow}>
                {readPath(design, field.path)
                  ? <Image source={{ uri: `${API_URL}${readPath(design, field.path)}` }}
                           style={st.logo} resizeMode="contain" />
                  : <View style={[st.logo, st.center]}>
                      <Ionicons name="image-outline" size={18} color="#94A3B8" />
                    </View>}
                <View style={{ flex: 1 }}>
                  <Text style={st.label}>{field.label}</Text>
                  <TouchableOpacity onPress={uploadLogo} disabled={photoBusy}
                                    testID="design-logo" style={st.linkBtn}>
                    <Text style={st.linkBtnText}>
                      {readPath(design, field.path) ? 'Cambiar' : 'Subir mi logo'}
                    </Text>
                  </TouchableOpacity>
                </View>
                {!!readPath(design, field.path) && (
                  <TouchableOpacity onPress={() => clearField(field)} hitSlop={10} style={st.clearBtn}
                                    testID={`clear-${field.path}`}>
                    <Ionicons name="trash-outline" size={16} color="#94A3B8" />
                  </TouchableOpacity>
                )}
              </View>
            ) : (
              <View key={field.path}>
                <View style={st.labelRow}>
                  <Text style={st.label}>{field.label}</Text>
                  {field.removable && !!readPath(design, field.path) && (
                    <TouchableOpacity onPress={() => clearField(field)} hitSlop={10}
                                      testID={`clear-${field.path}`}>
                      <Text style={st.clearText}>Quitar</Text>
                    </TouchableOpacity>
                  )}
                </View>
                <TextInput
                  style={st.input}
                  value={String(readPath(design, field.path) ?? '')}
                  onChangeText={text => setField(field.path, text)}
                  onBlur={() => saveFields()}
                  placeholder={field.placeholder || ''}
                  placeholderTextColor="#CBD5E1"
                  keyboardType={field.kind === 'url' ? 'url' : 'default'}
                  autoCapitalize={field.kind === 'url' ? 'none' : 'sentences'}
                  testID={`field-${field.path}`}
                />
              </View>
            ))}
          </View>
        ))}

        {editor.categories.map(section => {
          const category = design?.bindings?.categories?.[section.index] || {};
          const ids: string[] = category.product_ids || [];
          return (
            <View key={section.index} style={st.catBlock}>
              {section.has_header ? (
                <View style={st.catHead}>
                  <TextInput
                    style={st.catInput}
                    value={String(category.name ?? '')}
                    onChangeText={text => setField(section.name_path, text)}
                    onBlur={() => saveFields()}
                    placeholder="Nombre de la sección"
                    placeholderTextColor="#DDD6FE"
                    testID={`category-${section.index}`}
                  />
                </View>
              ) : <Text style={st.catTitle}>Sección {section.index + 1}</Text>}

              {ids.map((pid: string) => {
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

              <TouchableOpacity style={st.addRow} onPress={() => addProduct(section.index)}
                                testID={`add-product-${section.index}`}>
                <Ionicons name="add-circle-outline" size={18} color="#6D28D9" />
                <Text style={st.addRowText}>
                  Agregar producto
                  {section.slots ? ` · esta sección muestra ${section.slots}` : ''}
                </Text>
              </TouchableOpacity>
            </View>
          );
        })}
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
              <ScrollView style={{ maxHeight: height * 0.66 }} keyboardShouldPersistTaps="handled">
              {/* La misma cartelera del TV, acá, cambiando en vivo: el dueño ve
                  si el nombre largo o el precio nuevo le entran en la tarjeta
                  antes de guardar. */}
              <HtmlPreview
                html={html}
                canvasW={canvas.w}
                canvasH={canvas.h}
                maxWidth={Math.min(width, 900) - 76}
                maxHeight={Math.min(height * 0.26, 240)}
                loading={previewBusy}
                testID="design-sheet-preview"
              />
              {!!draft?.image_url && shows('image') && (
                <Image source={{ uri: `${API_URL}${draft.image_url}` }} style={st.bigPhoto} />
              )}
              {shows('image') && (
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
              )}
              <Text style={st.label}>Nombre</Text>
              <TextInput
                style={st.input} value={draft?.name || ''}
                onChangeText={text => setDraft(d => d && { ...d, name: text })}
                testID="design-product-name"
              />
              {shows('description') && (
                <>
                  <Text style={st.label}>Ingredientes / descripción</Text>
                  <TextInput
                    style={[st.input, st.inputMulti]}
                    value={draft?.description || ''}
                    onChangeText={text => setDraft(d => d && { ...d, description: text })}
                    placeholder="Doble pepperoni, mozzarella y orégano"
                    placeholderTextColor="#CBD5E1"
                    multiline
                    testID="design-product-desc"
                  />
                </>
              )}
              {shows('badge') && (
                <>
                  <Text style={st.label}>Etiqueta sobre la foto</Text>
                  <TextInput
                    style={st.input} value={draft?.badge || ''}
                    onChangeText={text => setDraft(d => d && { ...d, badge: text })}
                    placeholder="La más pedida (dejalo vacío para no mostrarla)"
                    placeholderTextColor="#CBD5E1"
                    testID="design-product-badge"
                  />
                </>
              )}
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
              </ScrollView>
              <TouchableOpacity
                style={[st.saveBtn, saving && { opacity: 0.6 }]}
                onPress={saveProduct} disabled={saving}
                testID="design-product-save"
              >
                {saving ? <ActivityIndicator size={15} color="#fff" />
                        : <Text style={st.saveBtnText}>Guardar</Text>}
              </TouchableOpacity>
              <TouchableOpacity
                style={st.removeBtn}
                onPress={() => editing && removeProduct(editing)}
                testID="design-product-remove"
              >
                <Ionicons name="trash-outline" size={15} color="#DC2626" />
                <Text style={st.removeBtnText}>Quitar este producto</Text>
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
  topSubOk: { color: '#059669' },
  iconBtn: { width: 40, height: 40, borderRadius: 10, justifyContent: 'center', alignItems: 'center', backgroundColor: '#F5F3FF' },
  pubBtn: { backgroundColor: '#7C3AED', paddingHorizontal: 14, minHeight: 40, borderRadius: 10, justifyContent: 'center' },
  pubBtnText: { color: '#fff', fontSize: 13, fontWeight: '700' },

  body: { padding: 16, gap: 16 },
  previewCard: {
    backgroundColor: '#FFFFFF', borderRadius: 14, borderWidth: 1, borderColor: '#E2E8F0',
    padding: 14, gap: 10,
  },
  previewHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  previewTitle: { fontSize: 12, fontWeight: '800', color: '#64748B', textTransform: 'uppercase', letterSpacing: 0.5 },
  previewLink: { fontSize: 12, fontWeight: '800', color: '#6D28D9' },
  brandCard: { backgroundColor: '#FFFFFF', borderRadius: 14, borderWidth: 1, borderColor: '#E2E8F0', padding: 14, gap: 6 },
  groupTitle: { fontSize: 13, fontWeight: '800', color: '#0F172A' },
  labelRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  clearText: { fontSize: 11, fontWeight: '800', color: '#DC2626', marginTop: 8 },
  clearBtn: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  logoRow: { flexDirection: 'row', alignItems: 'center', gap: 12, marginTop: 8 },
  logo: { width: 56, height: 56, borderRadius: 10, backgroundColor: '#F1F5F9' },
  linkBtn: { minHeight: 36, justifyContent: 'center' },
  linkBtnText: { fontSize: 13, fontWeight: '800', color: '#6D28D9' },
  inputMulti: { minHeight: 74, paddingTop: 10, textAlignVertical: 'top' },
  catHead: { paddingHorizontal: 8, paddingTop: 8 },
  catInput: {
    fontSize: 13, fontWeight: '800', color: '#6D28D9', textTransform: 'uppercase',
    letterSpacing: 0.7, paddingHorizontal: 6, minHeight: 44,
  },
  addRow: {
    flexDirection: 'row', alignItems: 'center', gap: 8, minHeight: 48,
    paddingHorizontal: 14, borderTopWidth: 1, borderTopColor: '#F1F5F9',
  },
  addRowText: { fontSize: 13, fontWeight: '700', color: '#6D28D9' },
  removeBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 7,
    minHeight: 44, marginTop: 8,
  },
  removeBtnText: { fontSize: 13, fontWeight: '700', color: '#DC2626' },
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
