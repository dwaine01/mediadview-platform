/**
 * editTarget.ts — de «esto se está viendo en la tele» a «acá lo edito».
 *
 * El backend ya dice, para cada pantalla, qué hay al aire y de qué se edita
 * (`edit_kind` + `edit_id`, derivados del `media_id` del contrato del
 * reproductor). Esta función es el único lugar que traduce eso a una ruta del
 * panel, así el dueño llega al editor desde la pantalla, desde el inicio o
 * desde la lista de menús sin pasar por ningún catálogo.
 */
export type EditTarget = {
  edit_kind?: 'design' | 'menu' | null;
  edit_id?: string | null;
  title?: string | null;
};

export function editRoute(target?: EditTarget | null): string | null {
  if (!target?.edit_id || !target?.edit_kind) return null;
  return target.edit_kind === 'design'
    ? `/workspace/design-edit?id=${target.edit_id}`
    : `/workspace/menu-edit?id=${target.edit_id}`;
}

/** Lo editable de una pantalla: lo que está al aire ahora y, si no, el resto. */
export function screenEditTarget(screen?: {
  now_playing?: EditTarget | null;
  editables?: EditTarget[] | null;
} | null): EditTarget | null {
  if (editRoute(screen?.now_playing)) return screen!.now_playing!;
  return (screen?.editables || []).find(item => editRoute(item)) || null;
}
