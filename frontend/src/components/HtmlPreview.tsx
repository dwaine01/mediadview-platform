/**
 * HtmlPreview.tsx — la cartelera tal como la ve el TV, dentro del panel.
 *
 * El HTML que genera el motor se escala solo al tamaño de su ventana (lo hace
 * el `fit()` de la propia página), así que acá sólo hace falta darle una caja
 * con la proporción del lienzo. En web eso es un `iframe` de verdad; en el
 * celular, un WebView.
 */
import React from 'react';
import { View, Text, StyleSheet, ActivityIndicator, Platform } from 'react-native';
import { WebView } from 'react-native-webview';

type Props = {
  html?: string | null;
  /** Alternativa al HTML: la URL del render (el catálogo la usa así). */
  url?: string | null;
  /** Lienzo de la plantilla, para respetar la proporción del TV. */
  canvasW: number;
  canvasH: number;
  maxWidth: number;
  maxHeight: number;
  loading?: boolean;
  testID?: string;
};

export default function HtmlPreview({
  html, url, canvasW, canvasH, maxWidth, maxHeight, loading, testID,
}: Props) {
  const ratio = canvasW > 0 && canvasH > 0 ? canvasW / canvasH : 16 / 9;
  const width = Math.min(maxWidth, maxHeight * ratio);
  const height = width / ratio;
  const ready = !!(html || url);

  return (
    <View style={[hp.box, { width, height }]} testID={testID}>
      {ready
        ? (Platform.OS === 'web'
            ? React.createElement('iframe', {
                ...(url ? { src: url } : { srcDoc: html }),
                // El render es nuestro y necesita su script de escalado.
                sandbox: 'allow-scripts allow-same-origin',
                scrolling: 'no',
                style: {
                  width: '100%', height: '100%', border: 0, display: 'block',
                  // En el catálogo la miniatura es una foto, no algo que se toca.
                  pointerEvents: url ? 'none' : 'auto',
                },
                title: 'Vista previa',
              })
            : <WebView
                source={url ? { uri: url } : { html: html || '' }}
                style={hp.web}
                scrollEnabled={false}
                pointerEvents={url ? 'none' : 'auto'}
                originWhitelist={['*']}
                javaScriptEnabled
              />)
        : (
          <View style={hp.empty}>
            {loading
              ? <ActivityIndicator color="#A78BFA" />
              : <Text style={hp.emptyText}>Vista previa</Text>}
          </View>
        )}
      {!!html && loading && (
        <View style={hp.spinner}><ActivityIndicator size="small" color="#FFFFFF" /></View>
      )}
    </View>
  );
}

const hp = StyleSheet.create({
  box: {
    alignSelf: 'center', borderRadius: 12, overflow: 'hidden',
    backgroundColor: '#0B0908', borderWidth: 1, borderColor: '#1E293B',
  },
  web: { flex: 1, backgroundColor: '#0B0908' },
  empty: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  emptyText: { fontSize: 12, color: '#64748B', fontWeight: '600' },
  spinner: {
    position: 'absolute', top: 8, right: 8, width: 26, height: 26, borderRadius: 13,
    alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(15,23,42,0.6)',
  },
});
