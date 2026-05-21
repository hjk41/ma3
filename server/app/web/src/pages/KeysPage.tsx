import { FormEvent, useEffect, useMemo, useState } from 'react';
import { api } from '../api/client';
import { Badge, Button, Card, Empty, ErrorMessage, HelpText, Modal } from '../components/ui';
import { useUser } from '../contexts/UserContext';

function toIsoOrNull(value: FormDataEntryValue | null) {
  const raw = String(value || '').trim();
  if (!raw) return null;
  const date = new Date(raw);
  return Number.isNaN(date.getTime()) ? raw : date.toISOString();
}

export function KeysPageContent({ compact = false }: { compact?: boolean }) {
  const { whoami } = useUser();
  const [keys, setKeys] = useState<any[]>([]);
  const [open, setOpen] = useState(false);
  const [raw, setRaw] = useState('');
  const [rawLabel, setRawLabel] = useState('');
  const [error, setError] = useState('');
  const [scopeMode, setScopeMode] = useState<'all' | 'selected'>('all');
  const [selectedLibraries, setSelectedLibraries] = useState<string[]>([]);

  const canCreateKey = whoami?.principal.kind !== 'admin';
  const libraries = useMemo(() => whoami?.libraries || [], [whoami]);

  useEffect(() => {
    api.listKeys().then(setKeys).catch(() => setKeys([]));
  }, []);

  useEffect(() => {
    if (selectedLibraries.length === 0 && libraries.length > 0) {
      setSelectedLibraries(libraries.map((library: any) => library.library_id));
    }
  }, [libraries]);

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');
    const fd = new FormData(event.currentTarget);
    const scope = scopeMode === 'selected' ? selectedLibraries : null;
    if (scopeMode === 'selected' && selectedLibraries.length === 0) {
      setError('Select at least one library or use all accessible libraries.');
      return;
    }
    try {
      const issued = await api.createKey({
        label: fd.get('label'),
        scope_libraries: scope,
        expires_at: toIsoOrNull(fd.get('expires_at')),
      });
      setRaw(issued.raw);
      setRawLabel(issued.info?.label || String(fd.get('label') || 'new key'));
      setKeys([issued.info, ...keys]);
      setOpen(false);
    } catch (err: any) {
      setError(err.message || 'Failed to create key');
    }
  }

  async function revoke(id: string) {
    if (!window.confirm(`Revoke ${id}? Agents using it will stop working.`)) return;
    await api.revokeKey(id);
    setKeys(keys.filter(key => key.key_id !== id));
  }

  function toggleLibrary(libraryId: string) {
    setSelectedLibraries(current =>
      current.includes(libraryId)
        ? current.filter(item => item !== libraryId)
        : [...current, libraryId],
    );
  }

  return (
    <Card
      title={compact ? 'API keys' : 'API keys'}
      actions={canCreateKey ? <Button onClick={() => setOpen(true)}>Create key</Button> : null}
    >
      <Modal open={open} onClose={() => setOpen(false)} title="Create API key">
        <form onSubmit={create} className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">Label</label>
            <input
              name="label"
              required
              placeholder="agent name or machine purpose"
              className="w-full border rounded px-3 py-2"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Scope</label>
            <div className="space-y-2 text-sm">
              <label className="flex items-center gap-2">
                <input type="radio" checked={scopeMode === 'all'} onChange={() => setScopeMode('all')} />
                All libraries this principal can access
              </label>
              <label className="flex items-center gap-2">
                <input type="radio" checked={scopeMode === 'selected'} onChange={() => setScopeMode('selected')} />
                Selected libraries only
              </label>
            </div>
            {scopeMode === 'selected' && (
              <div className="mt-2 max-h-36 overflow-auto rounded border divide-y">
                {libraries.map((library: any) => (
                  <label key={library.library_id} className="flex items-center gap-2 px-3 py-2 text-sm">
                    <input
                      type="checkbox"
                      checked={selectedLibraries.includes(library.library_id)}
                      onChange={() => toggleLibrary(library.library_id)}
                    />
                    <span className="flex-1">
                      {library.name || library.library_id}
                      <code className="ml-2 text-xs text-slate-400">{library.library_id}</code>
                    </span>
                  </label>
                ))}
              </div>
            )}
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Expires at (optional)</label>
            <input name="expires_at" type="datetime-local" className="w-full border rounded px-3 py-2" />
          </div>
          <div className="rounded-md border border-yellow-200 bg-yellow-50 p-3 text-sm text-yellow-800">
            The raw secret is shown once after creation. Copy it before leaving this page.
          </div>
          <Button>Create</Button>
        </form>
      </Modal>

      <div className="space-y-4">
        {error && <ErrorMessage message={error} />}
        {!canCreateKey && (
          <ErrorMessage message="Root admin credentials cannot self-issue user API keys. Sign in as a user or create a service principal from Admin." />
        )}
        {raw && (
          <div className="rounded-md border border-yellow-200 bg-yellow-50 p-4">
            <div className="font-semibold text-yellow-900">Copy this secret now: {rawLabel}</div>
            <HelpText>This value will not be returned again by the server.</HelpText>
            <pre className="mt-3 overflow-auto rounded bg-white p-3 text-sm"><code>{raw}</code></pre>
          </div>
        )}

        {keys.length ? (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-slate-400">
                <th className="pb-2">Key</th>
                <th className="pb-2">Label</th>
                <th className="pb-2">Scope</th>
                <th className="pb-2">Status</th>
                <th className="pb-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {keys.map(key => (
                <tr key={key.key_id} className="border-b last:border-0">
                  <td className="py-2"><code>{key.key_id}</code></td>
                  <td>{key.label}</td>
                  <td>{(key.scope_libraries || []).join(', ') || 'all accessible'}</td>
                  <td>{key.revoked_at ? <Badge label="revoked" color="red" /> : <Badge label="active" color="green" />}</td>
                  <td className="text-right">
                    <Button variant="secondary" className="text-red-700 hover:bg-red-50" onClick={() => revoke(key.key_id)}>
                      Revoke
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <Empty
            title="No API keys yet"
            message="Create a scoped key for an agent, service, or local tool. Keys can be limited to selected libraries."
            action={canCreateKey ? <Button onClick={() => setOpen(true)}>Create first key</Button> : null}
          />
        )}
      </div>
    </Card>
  );
}

export function KeysPage() {
  return (
    <div className="max-w-5xl mx-auto px-8 py-8">
      <KeysPageContent />
    </div>
  );
}
