/**
 * In-memory branding cache — replaces localStorage-based tenant_branding_cache
 * to prevent potential information leakage via persistent storage.
 *
 * Branding data (product name, welcome text) is fetched from the API and held
 * in memory for the current session only.  On page refresh it is re-fetched.
 */

interface BrandingData {
  product_name?: string
  welcome_text?: string
  [key: string]: unknown
}

let _cache: BrandingData | null = null

/** Get cached branding data (or null if not yet loaded). */
export function getBrandingCache(): BrandingData | null {
  return _cache
}

/** Store branding data in memory. */
export function setBrandingCache(data: BrandingData): void {
  _cache = data ? { ...data } : null
}

/** Clear the branding cache (e.g. on logout). */
export function clearBrandingCache(): void {
  _cache = null
}
