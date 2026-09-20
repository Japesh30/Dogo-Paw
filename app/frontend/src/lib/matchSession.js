/**
 * The visitor's last completed questionnaire and its results, kept for the
 * length of the tab.
 *
 * A dog's profile page wants to show "here is how you scored against *this*
 * dog" without sending the person back through the five questions. The obvious
 * implementation — re-POST /api/recommend from the profile page — is wrong:
 * that endpoint writes a MatchRequest audit row on every call, so simply
 * browsing dog pages would inflate the admin dashboard's numbers with
 * recommendations nobody asked for.
 *
 * So /adopt-match stores its own response instead. The profile page and the
 * gallery read the score straight out of it, which costs no request and cannot
 * disagree with what the visitor already saw. It also lets /adopt-match itself
 * restore the results when they navigate back to it.
 *
 * sessionStorage rather than localStorage: a matching profile is a "right now"
 * thing, and it should not still be sitting there tomorrow claiming to describe
 * the household. The whole payload is ~20 kB, well inside the quota.
 */
const KEY = 'dogopaw.match'

export function saveMatchSession({ adopter, matches, count }) {
  try {
    sessionStorage.setItem(
      KEY,
      JSON.stringify({ adopter, matches, count: count ?? matches.length }),
    )
  } catch {
    // Private mode, or storage full. The site works without this; the profile
    // page just falls back to the "take the quiz" call to action.
  }
}

export function readMatchSession() {
  try {
    const raw = sessionStorage.getItem(KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!parsed?.adopter || !Array.isArray(parsed?.matches)) return null
    return parsed
  } catch {
    return null
  }
}

/** dog_id -> match, for the gallery's score badges. */
export function scoresByDog(session) {
  const map = {}
  for (const m of session?.matches ?? []) map[m.dog_id] = m
  return map
}

/** The stored match for one dog, or null if there is no session for it. */
export function scoreForDog(dogId) {
  return scoresByDog(readMatchSession())[dogId] ?? null
}

export function clearMatchSession() {
  try {
    sessionStorage.removeItem(KEY)
  } catch {
    /* nothing to do */
  }
}
