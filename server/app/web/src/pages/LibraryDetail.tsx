import { FormEvent, useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { api } from '../api/client';
import { Badge, Button, Card, Empty, ErrorMessage, HelpText, Modal } from '../components/ui';
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

type RecordPreview = {
  record_id: string;
  library_id?: string | null;
  title?: string;
  summary?: string;
  status?: string;
  tags?: string[];
  risk_level?: string;
  updated_at?: string;
};

const ROLE_NAME_TO_LIBRARY_ROLE: Record<string, string> = {
  library_reader: 'reader',
  library_writer: 'writer',
  library_admin: 'admin',
};
const ROLE_ORDER = ['reader', 'writer', 'admin'];

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

function principalKind(principalId: string, principal?: Principal) {
  if (principal?.kind) return principal.kind;
  if (principalId.startsWith('legacy:tok_')) return 'legacy token';
  if (principalId.startsWith('legacy:lib:')) return 'legacy library';
  if (principalId.startsWith('user:')) return 'user';
  return 'principal';
}

export function LibraryDetail() {
  const { id } = useParams();
  const { whoami } = useUser();
  const [lib, setLib] = useState<any>();
  const [acl, setAcl] = useState<any[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [records, setRecords] = useState<RecordPreview[]>([]);
  const [recordsError, setRecordsError] = useState('');
  const [modalOpen, setModalOpen] = useState(false);
  const [principalId, setPrincipalId] = useState('');
  const [newRole, setNewRole] = useState('reader');
  const [suggestions, setSuggestions] = useState<Principal[]>([]);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [saveNotice, setSaveNotice] = useState('');

  const isAdmin = canManageLibrary(whoami, id);
  const libraryRoles = useMemo(() => {
    const values = roles
      .filter(role => role.scope_type === 'library')
      .map(role => ROLE_NAME_TO_LIBRARY_ROLE[role.role_name])
      .filter(Boolean);
    const unique = Array.from(new Set(values.length ? values : ROLE_ORDER));
    return ROLE_ORDER.filter(role => unique.includes(role));
  }, [roles]);

  async function loadAcl() {
    if (!id) return;
    setAcl(await api.listAcl(id).catch(() => []));
  }

  async function loadRecords() {
    if (!id) return;
    setRecordsError('');
    try {
      const page = await api.listRecords(`library_id=${encodeURIComponent(id)}&limit=5&status=active`);
      setRecords(page.records || []);
    } catch (err: any) {
      setRecords([]);
      setRecordsError(err.message || 'Records preview is unavailable.');
    }
  }

  useEffect(() => {
    if (!id) return;
    api.getLibrary(id).then(setLib);
    loadAcl();
    loadRecords();
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
    setSaveNotice('Saving access change…');
    setSaving(true);
    try {
      await api.grantAcl(id, targetPrincipalId, role);
      await loadAcl();
      setSaveNotice(`Saved ${targetPrincipalId} as ${role}.`);
    } catch (err: any) {
      setSaveNotice('');
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
    setSaveNotice('Removing access…');
    setSaving(true);
    try {
      await api.revokeAcl(id, targetPrincipalId);
      await loadAcl();
      setSaveNotice(`Removed ${targetPrincipalId}.`);
    } catch (err: any) {
      setSaveNotice('');
      setError(err.message || 'Failed to remove ACL');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="max-w-5xl mx-auto px-8 py-8 space-y-6">
      <Card title={lib?.name || id}>
        <div className="space-y-2">
          <p className="text-slate-600">{lib?.description || 'No description provided.'}</p>
          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400">
            <code>{lib?.library_id || id}</code>
            {lib?.is_public && <Badge label="public" color="green" />}
          </div>
        </div>
      </Card>

      {error && <ErrorMessage message={error} />}
      {saveNotice && <div className="rounded-md border border-blue-100 bg-blue-50 px-3 py-2 text-sm text-blue-700">{saveNotice}</div>}

      <Card title="Knowledge preview">
        <div className="space-y-4">
          <HelpText>Showing up to five active records from this library. Use MCP tools for full search and agent context.</HelpText>
          {recordsError ? (
            <ErrorMessage message={recordsError} />
          ) : records.length ? (
            <div className="divide-y divide-slate-100 rounded border border-slate-100">
              {records.map(record => (
                <div key={record.record_id} className="p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="font-medium text-slate-800">{record.title || record.record_id}</div>
                      <code className="text-xs text-slate-400">{record.record_id}</code>
                    </div>
                    <div className="flex gap-1 shrink-0">
                      {record.status && <Badge label={record.status} />}
                      {record.risk_level && <Badge label={record.risk_level} color={record.risk_level === 'high' ? 'red' : 'slate'} />}
                    </div>
                  </div>
                  {record.summary && <p className="mt-2 text-sm text-slate-600 line-clamp-2">{record.summary}</p>}
                  {record.tags?.length ? (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {record.tags.slice(0, 6).map(tag => <Badge key={tag} label={tag} />)}
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          ) : (
            <Empty title="No active records in preview" message="No accessible active records were returned for this library." />
          )}
        </div>
      </Card>

      <Card
        title="Members and access"
        actions={
          isAdmin ? (
            <Button onClick={() => setModalOpen(true)} disabled={saving}>
              Add principal
            </Button>
          ) : null
        }
      >
        <div className="space-y-3">
          <HelpText>Legacy token principals are migrated v2 library tokens. Prefer user or service principals for new grants.</HelpText>
          {acl.length ? (
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
                      <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400">
                        <code>{entry.principal_id}</code>
                        <Badge label={principalKind(entry.principal_id, entry.principal)} />
                      </div>
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
                    <td className="py-2 text-slate-500"><code className="text-xs">{entry.granted_by}</code></td>
                    {isAdmin && (
                      <td className="py-2 text-right">
                        <Button
                          variant="secondary"
                          className="text-red-700 hover:bg-red-50"
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
          ) : (
            <Empty title="No explicit ACL entries" message="Global admins can still manage this library. Add user or service principals for regular access." />
          )}
        </div>
      </Card>

      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title="Add principal">
        <form onSubmit={addPrincipal} className="space-y-3">
          <div>
            <label className="block text-sm font-medium mb-1">Principal ID</label>
            <input
              value={principalId}
              onChange={event => setPrincipalId(event.target.value)}
              className="w-full border rounded px-3 py-2"
              placeholder="user:alice or service:agent"
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
