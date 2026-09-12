/**
 * whenText.ts — fechas como las escribe y las lee el dueño del negocio.
 *
 * El panel trabaja con «24/12/2026 18:00» (hora del local) y el servidor con
 * ISO en UTC. Esta es la única traducción entre los dos mundos.
 */
const PATTERN = /^(\d{1,2})\/(\d{1,2})\/(\d{4})(?:[ ,]+(\d{1,2}):(\d{2}))?$/;

export function parseWhen(text: string): string | null {
  const match = PATTERN.exec(text.trim());
  if (!match) return null;
  const [, day, month, year, hour, minute] = match;
  const when = new Date(Number(year), Number(month) - 1, Number(day),
                        Number(hour ?? 0), Number(minute ?? 0), 0, 0);
  if (Number.isNaN(when.getTime()) || when.getDate() !== Number(day)) return null;
  return when.toISOString();
}

export function formatWhen(iso?: string | null): string {
  if (!iso) return '';
  const when = new Date(iso.endsWith('Z') || iso.includes('+') ? iso : `${iso}Z`);
  if (Number.isNaN(when.getTime())) return '';
  const pad = (value: number) => String(value).padStart(2, '0');
  return `${pad(when.getDate())}/${pad(when.getMonth() + 1)}/${when.getFullYear()} `
       + `${pad(when.getHours())}:${pad(when.getMinutes())}`;
}

/** «Del 24/12 18:00 al 26/12 23:59», en una línea corta para la lista. */
export function windowLabel(startsAt?: string | null, endsAt?: string | null): string {
  const short = (iso?: string | null) => formatWhen(iso).replace(/\/\d{4}/, '');
  if (startsAt && endsAt) return `Del ${short(startsAt)} al ${short(endsAt)}`;
  if (endsAt) return `Hasta el ${short(endsAt)}`;
  if (startsAt) return `Desde el ${short(startsAt)}`;
  return 'Sale siempre';
}

/** Fin de la jornada de hoy + los días que se pidan, para los atajos. */
export function inDays(days: number): string {
  const when = new Date();
  when.setDate(when.getDate() + days);
  when.setHours(23, 59, 0, 0);
  return when.toISOString();
}
