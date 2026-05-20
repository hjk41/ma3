import { FormEvent, useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { api } from '../api/client';
import { Badge, Button, Card, ErrorMessage, Modal } from '../components/ui';
import { useUser } from '../contexts/UserContext';

type Principal = {
  principal_id: string;
  kind: string;
  display_name?: string;
  sso_user?: string | null;
};

type Role = {
  role_name: string;
  scope_type: string;
};

const ROLE_NAME_TO_LIBRARY_ROLE: Record<string, string> = {
  library_reader: 'reader',
  library_writer: 'writer',
  library_admin: 'admin',
};

async function requestJson<T>(url: string): Promise<T> {
  const resp = await fetch(url, { credentials: 'include' });
  if (!resp.ok) {
    throw new Error(await resp.text());
  }
  return resp.json() as Promise<T>;
}

function canManageLibrary(whoami: any, libId?: string) {
  if (!whoami || !libId) return false;
  if (whoami.admin_bypass) return true;
  return (whoami.libraries || []).some(
    (item: any) => item.library_id === libId && item.role === 'admin',
  );
}

export function LibraryDetail() {
  const { id } = useParams();
  const { whoami } = useUser();
  const [lib, setLib] = useState<any>();
  const [acl, setAcl] = useState<any[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [modalOpen, setModalOpen] = useState(false);
  const [principalId, setPrincipalId] = useState('');
  const [newRole, setNewRole] = useState('reader');
  const [suggestions, setSuggestions] = useState<Principal[]>([]);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  const isAdmin = canManageLibrary(whoami, id);
  const libraryRoles = useMemo(() => {
    const values = roles
      .filter(role => role.scope_type === 'library')
      .map(role => ROLE_NAME_TO_LIBRARY_ROLE[role.role_name])
      .filter(Boolean);
    return values.length ? values : ['reader', 'writer', 'admin'];
  }, [roles]);

  async function loadAcl() {
    if (!id) return;
    setAcl(await api.listAcl(id).catch(() => []));
  }

  useEffect(() => {
    if (!id) return;
    api.getLibrary(id).then(setLib);
    loadAcl();
    api.listRoles().then(setRoles).catch(() => setRoles([]));
  }, [id]);

  useEffect(() => {
    if (!modalOpen || !principalId.trim()) {
      setSuggestions([]);
      return;
    }
    const handle = window.setTimeout(() => {
      requestJson<Principal[]>(
        `/v3/auth/principals?prefix=${encodeURIComponent(principalId.trim())}&limit=50`,
      )
        .then(setSuggestions)
        .catch(() => setSuggestions([]));
    }, 150);
    return () => window.clearTimeout(handle);
  }, [modalOpen, principalId]);

  async function changeRole(targetPrincipalId: string, role: string) {
    if (!id) return;
    setError('');
    setSaving(true);
    try {
      await api.grantAcl(id, targetPrincipalId, role);
      await loadAcl();
    } catch (err: any) {
      setError(err.message || 'Failed to update ACL');
    } finally {
      setSaving(false);
    }
  }

  async function addPrincipal(event: FormEvent) {
    event.preventDefault();
    if (!id || !principalId.trim()) return;
    await changeRole(principalId.trim(), newRole);
    setPrincipalId('');
    setNewRole('reader');
    setModalOpen(false);
  }

  async function removePrincipal(targetPrincipalId: string) {
    if (!id) return;
    if (!window.confirm(`Remove ${targetPrincipalId} from this library?`)) return;
    setError('');
    setSaving(true);
    try {
      await api.revokeAcl(id, targetPrincipalId);
      await loadAcl();
    } catch (err: any) {
      setError(err.message || 'Failed to remove ACL');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="max-w-5xl mx-auto px-8 py-8 space-y-6">
      <Card title={lib?.name || id}>
        <p className="text-slate-600">{lib?.description}</p>
        <p className="text-xs text-slate-400">{lib?.library_id}</p>
      </Card>

      {error && <ErrorMessage message={error} />}

      <Card
        title="ACL"
        actions={
          isAdmin ? (
            <Button onClick={() => setModalOpen(true)} disabled={saving}>
              Add principal
            </Button>
          ) : null
        }
      >
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wide text-slate-400">
              <th className="pb-2">Principal</th>
              <th className="pb-2">Role</th>
              <th className="pb-2">Granted by</th>
              {isAdmin && <th className="pb-2 text-right">Actions</th>}
            </tr>
          </thead>
          <tbody>
            {acl.map(entry => (
              <tr key={entry.principal_id} className="border-b last:border-0">
                <td className="py-2">
                  <div className="font-medium text-slate-800">
                    {entry.principal?.display_name || entry.principal_id}
                  </div>
                  <div className="text-xs text-slate-400">{entry.principal_id}</div>
                </td>
                <td className="py-2">
                  {isAdmin ? (
                    <select
                      value={entry.role}
                      onChange={event => changeRole(entry.principal_id, event.target.value)}
                      className="border rounded px-2 py-1 text-sm"
                      disabled={saving}
                    >
                      {libraryRoles.map(role => (
                        <option key={role} value={role}>
                          {role}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <Badge label={entry.role} />
                  )}
                </td>
                <td className="py-2 text-slate-500">{entry.granted_by}</td>
                {isAdmin && (
                  <td className="py-2 text-right">
                    <Button
                      variant="danger"
                      onClick={() => removePrincipal(entry.principal_id)}
                      disabled={saving}
                    >
                      Remove
                    </Button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Card title="Records preview">
        <p className="text-slate-400">First-page record preview placeholder for v3.1.</p>
      </Card>

      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title="Add principal">
        <form onSubmit={addPrincipal} className="space-y-3">
          <div>
            <label className="block text-sm font-medium mb-1">Principal ID</label>
            <input
              value={principalId}
              onChange={event => setPrincipalId(event.target.value)}
              className="w-full border rounded px-3 py-2"
              placeholder="user:alice"
              required
            />
            {suggestions.length > 0 && (
              <div className="mt-2 rounded border divide-y max-h-40 overflow-auto">
                {suggestions.map(principal => (
                  <button
                    key={principal.principal_id}
                    type="button"
                    onClick={() => setPrincipalId(principal.principal_id)}
                    className="block w-full text-left px-3 py-2 text-sm hover:bg-slate-50"
                  >
                    <span className="font-medium">{principal.principal_id}</span>
                    <span className="ml-2 text-slate-400">{principal.display_name}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Role</label>
            <select
              value={newRole}
              onChange={event => setNewRole(event.target.value)}
              className="w-full border rounded px-3 py-2"
            >
              {libraryRoles.map(role => (
                <option key={role} value={role}>
                  {role}
                </option>
              ))}
            </select>
          </div>
          <Button disabled={saving}>Grant access</Button>
        </form>
      </Modal>
    </div>
  );
}
