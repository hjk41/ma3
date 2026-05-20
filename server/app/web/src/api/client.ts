export class ForbiddenError extends Error {}

export type Whoami = { principal: { principal_id: string; kind: string; display_name: string }; via: string; libraries: any[]; roles: any[]; admin_bypass: boolean; api_key?: any };

async function request<T>(url: string, options: RequestInit = {}): Promise<T> {
  const resp = await fetch(url, { credentials: 'include', ...options, headers: { 'Content-Type': 'application/json', ...(options.headers || {}) } });
  if (resp.status === 401) { window.location.href = `/auth/login?next=${encodeURIComponent(window.location.pathname + window.location.search)}`; throw new Error('unauthorized'); }
  if (resp.status === 403) throw new ForbiddenError('forbidden');
  const text = await resp.text();
  if (!resp.ok) throw new Error(text || `${resp.status}`);
  return (text ? JSON.parse(text) : null) as T;
}

export const api = {
  whoami: () => request<Whoami>('/v3/auth/whoami'),
  permissions: () => request<any>('/v3/auth/permissions/me'),
  listRoles: () => request<any[]>('/v3/roles'),
  listLibraries: () => request<any[]>('/libraries'),
  getLibrary: (id: string) => request<any>(`/libraries/${id}`),
  createLibrary: (payload: any) => request<any>('/v3/libraries', { method: 'POST', body: JSON.stringify(payload) }),
  listAcl: (id: string) => request<any[]>(`/v3/libraries/${id}/acl`),
  grantAcl: (id: string, pid: string, role: string) => request<any>(`/v3/libraries/${id}/acl/${encodeURIComponent(pid)}`, { method: 'PUT', body: JSON.stringify({ role }) }),
  revokeAcl: (id: string, pid: string) => request<void>(`/v3/libraries/${id}/acl/${encodeURIComponent(pid)}`, { method: 'DELETE' }),
  listKeys: () => request<any[]>('/v3/auth/keys'),
  createKey: (payload: any) => request<any>('/v3/auth/keys', { method: 'POST', body: JSON.stringify(payload) }),
  revokeKey: (id: string) => request<void>(`/v3/auth/keys/${id}`, { method: 'DELETE' }),
  audit: () => request<any[]>('/v3/auth/audit?limit=50'),
  doctor: () => request<any>('/v2/doctor'),
  overview: () => request<any>('/v2/stats/overview'),
};
