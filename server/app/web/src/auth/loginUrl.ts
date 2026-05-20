export function buildLoginUrl(next = window.location.pathname + window.location.search) {
  return `/auth/login?next=${encodeURIComponent(next)}`;
}
