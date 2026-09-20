/**
 * Shared vocabulary for anything that displays a dog — the gallery, the profile
 * page, the home preview and the match results all read from here, so a dog is
 * described the same way wherever it appears.
 */

export const titleCase = (s = '') => s.charAt(0).toUpperCase() + s.slice(1)

/** Under a year reads better in months — "10 months old", not "0.8 years old". */
export function formatAge(age) {
  if (age == null) return ''
  if (age < 1) {
    const months = Math.round(age * 12)
    return `${months} ${months === 1 ? 'month' : 'months'}`
  }
  const rounded = Number.isInteger(age) ? age : age.toFixed(1)
  return `${rounded} ${age === 1 ? 'year' : 'years'}`
}

/** Energy runs low -> high, so the badge shades from quiet to loud. */
export const ENERGY_TONE = {
  low: 'bg-bark-100 text-bark-700',
  medium: 'bg-olive-100 text-olive-700',
  high: 'bg-amber-brand/25 text-amber-brand-dark',
}

export const SIZES = ['small', 'medium', 'large']
export const ENERGY_LEVELS = ['low', 'medium', 'high']

export const SIZE_HINT = {
  small: 'Suits a flat',
  medium: 'Flexible',
  large: 'Needs space',
}
