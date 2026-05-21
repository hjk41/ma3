import { ReactNode, useEffect, useState } from 'react';
import { api } from '../api/client';
import { Badge, Button, Card, ErrorMessage } from '../components/ui';
import { useUser } from '../contexts/UserContext';

type Tab = 'principals' | 'audit' | 'backup' | 'bulk';

type Principal = {
  principal_id: string;
  kind: string;
  display_name?: string;
  sso_user?: string | null;
};

async function requestJson<T>(url: string, options: RequestInit = {}): Promise<T> {
  const resp = await fetch(url, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json() as Promise<T>;
}

function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px ${
        active
          ? 'border-blue-600 text-blue-600'
          : 'border-transparent text-slate-500 hover:text-slate-700'
      }`}
    >
      {children}
    </button>
  );
}

function humanizeKey(key: string) {
  return key
    .replace(/_/g, ' ')
    .replace(/\b\w/g, char => char.toUpperCase());
}

function relativeTime(value: string | undefined) {
  if (!value) return '—';
  const time = new Date(value).getTime();
  if (Number.isNaN(time)) return value;
  const seconds = Math.max(0, Math.round((Date.now() - time) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

export function AdminConsole() {
  const { whoami } = useUser();
  const [tab, setTab] = useState<Tab>('principals');
  const [prefix, setPrefix] = useState('');
  const [principals, setPrincipals] = useState<Principal[]>([]);
  const [selected, setSelected] = useState<Principal | null>(null);
  const [selectedDetail, setSelectedDetail] = useState<any>(null);
  const [audit, setAudit] = useState<any[]>([]);
  const [backup, setBackup] = useState<any>({});
  const [usernames, setUsernames] = useState('');
  const [issued, setIssued] = useState<any[]>([]);
  const [error, setError] = useState('');

  async function searchPrincipals(nextPrefix = prefix) {
    setError('');
    try {
      setPrincipals(
        await requestJson<Principal[]>(
          `/v3/auth/principals?prefix=${encodeURIComponent(nextPrefix)}&limit=50`,
        ),
      );
    } catch (err: any) {
      setError(err.message || 'Failed to search principals');
    }
  }

  async function loadSelected(principal: Principal) {
    setSelected(principal);
    setSelectedDetail(null);
    try {
      setSelectedDetail(
        await requestJson(`/v3/auth/principals/${encodeURIComponent(principal.principal_id)}`),
      );
    } catch {
      setSelectedDetail({ roles: [], api_keys: [] });
    }
  }

  async function loadAudit(since?: string) {
    const url = since
      ? `/v3/auth/audit?limit=50&since=${encodeURIComponent(since)}`
      : '/v3/auth/audit?limit=50';
    const rows = await requestJson<any[]>(url);
    setAudit(prev => (since ? [...prev, ...rows] : rows));
  }

  async function issueKeys() {
    setError('');
    const names = usernames
      .split('\n')
      .map(item => item.trim())
      .filter(Boolean);
    if (!names.length) return;
    try {
      const result = await requestJson<any>('/v3/admin/issue_xyz_keys', {
        method: 'POST',
        body: JSON.stringify({ usernames: names }),
      });
      setIssued(result.items || result.issued || result);
    } catch (err: any) {
      setError(err.message || 'Failed to issue keys');
    }
  }

  useEffect(() => {
    if (!whoami?.admin_bypass) return;
    searchPrincipals('');
    loadAudit().catch(() => setAudit([]));
  }, [whoami]);

  useEffect(() => {
    if (!whoami?.admin_bypass) return;
    function loadBackup() {
      api.doctor()
        .then(data => setBackup(data?.backup || data?.['doctor.backup'] || data || {}))
        .catch(() => setBackup({ status: 'unavailable' }));
    }
    loadBackup();
    const handle = window.setInterval(loadBackup, 10_000);
    return () => window.clearInterval(handle);
  }, [whoami]);

  if (!whoami?.admin_bypass) {
    return (
      <div className="max-w-5xl mx-auto px-8 py-8">
        <Card title="Forbidden">Admin required.</Card>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto px-8 py-8 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">Admin console</h1>
        <p className="text-sm text-slate-500 mt-1">Principals, audit, backup status, and bulk XYZ key issuance.</p>
      </div>

      {error && <ErrorMessage message={error} />}

      <div className="flex border-b border-slate-200 bg-white px-2 rounded-t-lg">
        <TabButton active={tab === 'principals'} onClick={() => setTab('principals')}>Principals</TabButton>
        <TabButton active={tab === 'audit'} onClick={() => setTab('audit')}>Audit</TabButton>
        <TabButton active={tab === 'backup'} onClick={() => setTab('backup')}>Backup</TabButton>
        <TabButton active={tab === 'bulk'} onClick={() => setTab('bulk')}>Bulk xyz keys</TabButton>
      </div>

      {tab === 'principals' && (
        <div className="grid grid-cols-3 gap-4">
          <Card title="Principals">
            <div className="flex gap-2 mb-3">
              <input
                value={prefix}
                onChange={event => setPrefix(event.target.value)}
                onKeyDown={event => {
                  if (event.key === 'Enter') searchPrincipals();
                }}
                className="flex-1 border rounded px-3 py-2 text-sm"
                placeholder="prefix, e.g. user:a"
              />
              <Button onClick={() => searchPrincipals()}>Search</Button>
            </div>
            <div className="divide-y">
              {principals.map(principal => (
                <button
                  key={principal.principal_id}
                  onClick={() => loadSelected(principal)}
                  className="block w-full text-left py-2 hover:bg-slate-50"
                >
                  <div className="font-medium text-slate-800">{principal.principal_id}</div>
                  <div className="text-xs text-slate-400">
                    {principal.kind} · {principal.display_name || '—'} · {principal.sso_user || '—'}
                  </div>
                </button>
              ))}
            </div>
          </Card>

          <div className="col-span-2">
            <Card title={selected ? `Principal: ${selected.principal_id}` : 'Principal detail'}>
              {!selected ? (
                <p className="text-sm text-slate-400">Select a principal to inspect assignments and keys.</p>
              ) : (
                <div className="space-y-5">
                  <div className="flex gap-2">
                    <Badge label={selected.kind} color="blue" />
                    {selected.sso_user && <Badge label={selected.sso_user} />}
                  </div>
                  <div>
                    <h4 className="text-sm font-semibold mb-2">Role assignments</h4>
                    {(selectedDetail?.roles || []).length === 0 ? (
                      <p className="text-sm text-slate-400">No role assignments returned.</p>
                    ) : (
                      <table className="w-full text-sm">
                        <tbody>
                          {selectedDetail.roles.map((role: any) => (
                            <tr key={`${role.scope_type}:${role.scope_id}:${role.role_name}`} className="border-b">
                              <td className="py-2">{role.role_name}</td>
                              <td>{role.scope_type}</td>
                              <td>{role.scope_id || 'global'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </div>
                  <div>
                    <h4 className="text-sm font-semibold mb-2">API keys</h4>
                    {(selectedDetail?.api_keys || []).length === 0 ? (
                      <p className="text-sm text-slate-400">No API keys returned.</p>
                    ) : (
                      <table className="w-full text-sm">
                        <tbody>
                          {selectedDetail.api_keys.map((key: any) => (
                            <tr key={key.key_id} className="border-b">
                              <td className="py-2"><code>{key.key_id}</code></td>
                              <td>{key.label}</td>
                              <td>{key.revoked_at ? 'revoked' : 'active'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </div>
                </div>
              )}
            </Card>
          </div>
        </div>
      )}

      {tab === 'audit' && (
        <Card title="Audit">
          <p className="mb-4 text-sm text-slate-500">
            Latest authorization and administration events. Use Load more for older rows.
          </p>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-slate-400">
                <th className="pb-2">Time</th>
                <th className="pb-2">Actor</th>
                <th className="pb-2">Action</th>
                <th className="pb-2">Target</th>
                <th className="pb-2">Library</th>
              </tr>
            </thead>
            <tbody>
              {audit.map(row => (
                <tr key={row.audit_id} className="border-b last:border-0">
                  <td className="py-2 text-xs text-slate-500" title={row.created_at}>{relativeTime(row.created_at)}</td>
                  <td><code className="text-xs">{row.actor_principal_id}</code></td>
                  <td><Badge label={row.action} color="blue" /></td>
                  <td>{row.target_principal_id ? <code className="text-xs">{row.target_principal_id}</code> : '—'}</td>
                  <td>{row.library_id ? <code className="text-xs">{row.library_id}</code> : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-4">
            <Button
              variant="secondary"
              onClick={() => loadAudit(audit[audit.length - 1]?.created_at)}
              disabled={!audit.length}
            >
              Load more
            </Button>
          </div>
        </Card>
      )}

      {tab === 'backup' && (
        <Card title="Backup">
          <div className="space-y-4">
            <div className={`rounded-md border p-3 ${backup?.degraded ? 'border-yellow-200 bg-yellow-50' : 'border-green-200 bg-green-50'}`}>
              <div className="flex items-center gap-2">
                <Badge label={backup?.degraded ? 'Degraded' : 'Healthy'} color={backup?.degraded ? 'yellow' : 'green'} />
                <span className="text-sm text-slate-700">
                  {backup?.degraded
                    ? 'Backup or WAL archiving is behind. Check /v2/doctor and the LTP backup cron before cutover.'
                    : 'Backup signals are currently healthy.'}
                </span>
              </div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
              {Object.entries(backup).map(([key, value]) => (
                <div key={key} className="rounded border border-slate-100 p-3">
                  <div className="text-xs uppercase tracking-wide text-slate-400">{humanizeKey(key)}</div>
                  <div className="mt-1 break-all text-slate-800">{String(value)}</div>
                  <div className="mt-1 text-[11px] text-slate-400">{key}</div>
                </div>
              ))}
            </div>
          </div>
        </Card>
      )}

      {tab === 'bulk' && (
        <Card title="Bulk xyz keys">
          <div className="space-y-3">
            <p className="text-sm text-slate-500">
              Enter one SSO username per line. Raw secrets are returned once; copy them immediately.
            </p>
            <textarea
              value={usernames}
              onChange={event => setUsernames(event.target.value)}
              className="w-full h-32 border rounded px-3 py-2 text-sm font-mono"
              placeholder="alice\nbob"
            />
            <Button onClick={issueKeys}>Issue</Button>
            {issued.length > 0 && (
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs uppercase tracking-wide text-slate-400">
                    <th className="pb-2">username</th>
                    <th className="pb-2">principal</th>
                    <th className="pb-2">raw secret</th>
                  </tr>
                </thead>
                <tbody>
                  {issued.map(item => (
                    <tr key={item.username || item.principal_id} className="border-b">
                      <td className="py-2">{item.username}</td>
                      <td>{item.principal_id}</td>
                      <td><code className="break-all text-xs">{item.raw}</code></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </Card>
      )}
    </div>
  );
}
