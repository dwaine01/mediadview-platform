/**
 * signage-templates.tsx — catálogo de plantillas profesionales de MediaView.
 *
 * El cliente elige su rubro, ve las plantillas con su contenido de muestra real
 * (la misma página que va a mostrar el TV, no una maqueta) y arma su diseño en
 * un toque. Después reemplaza los productos de muestra por los suyos.
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, ActivityIndicator, FlatList, Linking,
  RefreshControl, useWindowDimensions,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import { workspaceAPI } from '../../src/services/api';
import AppDialog, { type DialogState } from '../../src/components/AppDialog';
import HtmlPreview from '../../src/components/HtmlPreview';

const API_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';

// Alto de la miniatura: igual para horizontales y verticales, así la galería
// queda prolija con plantillas de las dos formas mezcladas.
const THUMB_HEIGHT = 190;

const INDUSTRY_LABEL: Record<string, string> = {
  pizzeria: 'Pizzería',
  fast_food: 'Comida rápida',
  restaurant: 'Restaurante',
  ice_cream: 'Heladería',
  mexican: 'Mexicano',
  latin_honduras: 'Hondureño',
  latin_salvador: 'Salvadoreño',
  latin_panama: 'Panameño',
  latin_venezuela: 'Venezolano',
  tires: 'Gomería',
  seafood: 'Pescadería',
  pharmacy: 'Farmacia',
  offers: 'Ofertas flash',
  generic: 'General',
};

type Template = {
  id: string; name: string; tagline?: string; kind: string; industry: string;
  orientation: string; products?: number; animated?: boolean; preview_url: string;
};

export default function SignageTemplates() {
  const insets = useSafeAreaInsets();
  const { width } = useWindowDimensions();
  const [templates, setTemplates] = useState<Template[]>([]);
  const [industries, setIndustries] = useState<{ industry: string; templates: number }[]>([]);
  const [industry, setIndustry] = useState('');
  const [orientation, setOrientation] = useState('');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [usingId, setUsingId] = useState<string | null>(null);
  const [dialog, setDialog] = useState<DialogState>(null);

  const load = useCallback(async () => {
    try {
      const [list, rubros] = await Promise.all([
        workspaceAPI.signageTemplates({ industry: industry || undefined,
                                        orientation: orientation || undefined }),
        workspaceAPI.signageIndustries(),
      ]);
      setTemplates(list.data || []);
      setIndustries(rubros.data || []);
    } catch (e: any) {
      setDialog({ title: 'No pudimos cargar el catálogo',
                  message: e.response?.data?.detail || e.message });
    } finally { setLoading(false); setRefreshing(false); }
  }, [industry, orientation]);

  useEffect(() => { load(); }, [load]);

  // Miniaturas: el mismo render que ve el TV, traído una vez por plantilla y de
  // a una para no pedirle 20 tableros de golpe al servidor.
  const [thumbs, setThumbs] = useState<Record<string, string>>({});
  useEffect(() => {
    let alive = true;
    (async () => {
      for (const template of templates) {
        if (!alive) return;
        if (thumbs[template.id]) continue;
        try {
          const res = await workspaceAPI.templatePreviewHtml(template.id);
          if (!alive) return;
          setThumbs(prev => ({ ...prev, [template.id]: res.data }));
        } catch { /* una miniatura que falla no rompe el catálogo */ }
      }
    })();
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [templates]);

  const applyTemplate = async (template: Template) => {
    setUsingId(template.id);
    try {
      const res = await workspaceAPI.createDesign(template.id);
      router.push(`/workspace/design-edit?id=${res.data.design_id}`);
    } catch (e: any) {
      setDialog({ title: 'No se pudo usar la plantilla',
                  message: e.response?.data?.detail || e.message });
    } finally { setUsingId(null); }
  };

  // El preview es la misma página que renderiza el TV: se abre a pantalla
  // completa para que el cliente juzgue el diseño de verdad.
  const openPreview = (template: Template) =>
    Linking.openURL(`${API_URL}${template.preview_url}`);

  const cardWidth = Math.min(width, 900) - 32;

  const renderItem = ({ item }: { item: Template }) => {
    const portrait = item.orientation === 'portrait';
    // Miniatura del render real, con el contenido de muestra: el cliente
    // reconoce la plantilla de un vistazo en vez de leer un cuadro vacío.
    return (
      <TouchableOpacity
        style={st.card}
        onPress={() => applyTemplate(item)}
        activeOpacity={0.9}
        disabled={usingId === item.id}
        testID={`use-${item.id}`}
      >
        <View style={st.thumbBox}>
          <HtmlPreview
            html={thumbs[item.id] || null}
            canvasW={portrait ? 1080 : 1920}
            canvasH={portrait ? 1920 : 1080}
            maxWidth={cardWidth - 28}
            maxHeight={THUMB_HEIGHT}
            loading={!thumbs[item.id]}
            noInput
            testID={`thumb-${item.id}`}
          />
          {usingId === item.id && (
            <View style={st.thumbBusy}><ActivityIndicator color="#fff" /></View>
          )}
        </View>

        <View style={st.cardBody}>
          <View style={{ flex: 1 }}>
            <Text style={st.cardName} numberOfLines={1}>{item.name}</Text>
            <Text style={st.cardMeta} numberOfLines={1}>
              {[INDUSTRY_LABEL[item.industry] || item.industry,
                portrait ? 'Vertical' : 'Horizontal',
                item.products ? `${item.products} productos` : ''].filter(Boolean).join(' · ')}
            </Text>
          </View>
          <TouchableOpacity
            style={st.frameBtn}
            onPress={() => openPreview(item)}
            hitSlop={8}
            testID={`preview-${item.id}`}
          >
            <Ionicons name="expand-outline" size={14} color="#6D28D9" />
            <Text style={st.frameBtnText}>Ver grande</Text>
          </TouchableOpacity>
        </View>
      </TouchableOpacity>
    );
  };

  const Filters = (
    <View style={st.filters}>
      <FlatList
        horizontal
        showsHorizontalScrollIndicator={false}
        data={[{ industry: '', templates: 0 }, ...industries]}
        keyExtractor={row => row.industry || 'all'}
        contentContainerStyle={st.filterRow}
        renderItem={({ item }) => (
          <TouchableOpacity
            style={[st.fChip, industry === item.industry && st.fChipOn]}
            onPress={() => setIndustry(item.industry)}
            testID={`filter-${item.industry || 'all'}`}
          >
            <Text style={[st.fChipText, industry === item.industry && st.fChipTextOn]}>
              {item.industry ? (INDUSTRY_LABEL[item.industry] || item.industry) : 'Todos los rubros'}
            </Text>
          </TouchableOpacity>
        )}
      />
      <View style={st.filterRow}>
        {[['', 'Todas'], ['landscape', 'Horizontal'], ['portrait', 'Vertical']].map(([value, label]) => (
          <TouchableOpacity
            key={value || 'any'}
            style={[st.fChip, orientation === value && st.fChipOn]}
            onPress={() => setOrientation(value)}
            testID={`orient-${value || 'any'}`}
          >
            <Text style={[st.fChipText, orientation === value && st.fChipTextOn]}>{label}</Text>
          </TouchableOpacity>
        ))}
      </View>
    </View>
  );

  return (
    <View style={st.root}>
      <View style={[st.topBar, { paddingTop: insets.top + 8 }]}>
        <TouchableOpacity style={st.backBtn} onPress={() => router.back()} hitSlop={10}>
          <Ionicons name="arrow-back" size={20} color="#64748B" />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={st.topTitle}>Plantillas profesionales</Text>
          <Text style={st.topSub}>Elegí, reemplazá tus productos y publicá</Text>
        </View>
        <TouchableOpacity
          style={st.mineBtn}
          onPress={() => router.push('/workspace/menus')}
          testID="my-designs"
        >
          <Text style={st.mineBtnText}>Mis carteleras</Text>
        </TouchableOpacity>
      </View>

      {loading ? (
        <View style={st.center}><ActivityIndicator color="#7C3AED" size="large" /></View>
      ) : (
        <FlatList
          data={templates}
          keyExtractor={item => item.id}
          renderItem={renderItem}
          ListHeaderComponent={Filters}
          contentContainerStyle={[st.list, { paddingBottom: insets.bottom + 32 }]}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} />
          }
          ListEmptyComponent={
            <View style={st.empty}>
              <Ionicons name="albums-outline" size={30} color="#94A3B8" />
              <Text style={st.emptyText}>Todavía no hay plantillas para ese filtro.</Text>
            </View>
          }
        />
      )}

      <AppDialog state={dialog} onDismiss={() => setDialog(null)} />
    </View>
  );
}

const st = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#F8FAFC' },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  topBar: {
    flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 16, paddingBottom: 12,
    backgroundColor: '#FFFFFF', borderBottomWidth: 1, borderBottomColor: '#E2E8F0',
  },
  backBtn: { width: 36, height: 36, borderRadius: 10, justifyContent: 'center', alignItems: 'center', backgroundColor: '#F1F5F9' },
  topTitle: { fontSize: 16, fontWeight: '800', color: '#0F172A' },
  topSub: { fontSize: 11, color: '#64748B', fontWeight: '600' },
  mineBtn: { paddingHorizontal: 12, minHeight: 40, borderRadius: 10, justifyContent: 'center', backgroundColor: '#F5F3FF', borderWidth: 1, borderColor: '#DDD6FE' },
  mineBtnText: { color: '#6D28D9', fontSize: 12, fontWeight: '700' },

  filters: { gap: 8, paddingBottom: 4 },
  filterRow: { flexDirection: 'row', gap: 8, paddingVertical: 2 },
  fChip: { paddingHorizontal: 13, minHeight: 36, borderRadius: 999, backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#E2E8F0', justifyContent: 'center' },
  fChipOn: { backgroundColor: '#F5F3FF', borderColor: '#7C3AED' },
  fChipText: { fontSize: 12, fontWeight: '600', color: '#64748B' },
  fChipTextOn: { color: '#6D28D9' },

  list: { padding: 16, gap: 16 },
  card: { backgroundColor: '#FFFFFF', borderRadius: 16, borderWidth: 1, borderColor: '#E2E8F0', overflow: 'hidden' },
  thumbBox: { backgroundColor: '#0B0908', paddingVertical: 14, paddingHorizontal: 14, alignItems: 'center' },
  thumbBusy: { position: 'absolute', inset: 0, alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(15,23,42,0.55)' },
  cardBody: { flexDirection: 'row', alignItems: 'center', gap: 10, padding: 14 },
  cardName: { fontSize: 15, fontWeight: '800', color: '#0F172A' },
  cardMeta: { fontSize: 11.5, color: '#64748B', fontWeight: '600', marginTop: 2 },
  frameBtn: { flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 11, minHeight: 40, borderRadius: 999, backgroundColor: '#F5F3FF', borderWidth: 1, borderColor: '#DDD6FE', justifyContent: 'center' },
  frameBtnText: { fontSize: 12, fontWeight: '800', color: '#6D28D9' },

  empty: { alignItems: 'center', gap: 10, paddingTop: 50 },
  emptyText: { fontSize: 13, color: '#64748B' },
});
