/**
 * A screen's `location` is a plain string when the screen was created from the
 * customer panel, but a structured object ({address, city, state, country, lat,
 * lng}) when it was created from the admin API. Rendering the object directly
 * crashes React ("Objects are not valid as a React child"), so every screen
 * list has to go through this.
 */
export type ScreenLocation =
  | string
  | null
  | undefined
  | {
      address?: string | null;
      city?: string | null;
      state?: string | null;
      country?: string | null;
      lat?: number | null;
      lng?: number | null;
    };

export function formatScreenLocation(location: ScreenLocation): string {
  if (!location) return '';
  if (typeof location === 'string') return location.trim();
  return [location.address, location.city, location.state, location.country]
    .map(part => (part || '').trim())
    .filter(Boolean)
    .join(', ');
}
