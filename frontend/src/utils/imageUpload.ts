/**
 * imageUpload.ts — la foto que eligió el cliente, lista para subir.
 *
 * En el panel web una foto de celular moderna son 40 megapíxeles: en base64
 * eso es un JSON de ~30 MB que tumba al worker (el 502 clásico). Se reduce en
 * el navegador antes de salir. El hueco de foto de las plantillas se sirve a
 * 900 px, así que 1600 px de lado largo sobra y se sube en un segundo.
 */
import { Platform } from 'react-native';
import { File as FsFile } from 'expo-file-system';

export type PickedImage = {
  uri: string;
  base64?: string | null;
  mimeType?: string | null;
  file?: File | null;
};

const readAsDataUrl = (source: Blob) => new Promise<string>((resolve, reject) => {
  const reader = new FileReader();
  reader.onerror = () => reject(new Error('No pudimos leer la foto.'));
  reader.onload = () => resolve(String(reader.result || ''));
  reader.readAsDataURL(source);
});

export async function readPickedImage(
  asset: PickedImage, maxSide = 1600,
): Promise<{ base64: string; mime: string }> {
  const mime = (asset.mimeType || 'image/jpeg').toLowerCase();

  if (Platform.OS !== 'web') {
    if (asset.base64) return { base64: asset.base64, mime };
    return { base64: await new FsFile(asset.uri).base64(), mime };
  }

  const blob = asset.file ?? (await (await fetch(asset.uri)).blob());
  try {
    const bitmap = await createImageBitmap(blob);
    const ratio = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height));
    if (ratio === 1 && blob.size < 2 * 1024 * 1024) {
      bitmap.close?.();
      return { base64: (await readAsDataUrl(blob)).split(',')[1] || '', mime };
    }
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.round(bitmap.width * ratio));
    canvas.height = Math.max(1, Math.round(bitmap.height * ratio));
    const ctx = canvas.getContext('2d');
    if (!ctx) throw new Error('sin canvas');
    ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    bitmap.close?.();
    return {
      base64: canvas.toDataURL('image/jpeg', 0.9).split(',')[1] || '',
      mime: 'image/jpeg',
    };
  } catch {
    // Si el navegador no colabora, que decida el backend.
    return { base64: (await readAsDataUrl(blob)).split(',')[1] || '', mime };
  }
}
