import { FormEvent, useEffect, useState } from 'react';
import { api } from '../api/client';
import { Button, Card, Modal } from '../components/ui';

export function KeysPageContent({ compact = false }: { compact?: boolean }) {
  const [keys, setKeys] = useState<any[]>([]);
  const [open, setOpen] = useState(false);
  const [raw, setRaw] = useState('');

  useEffect(() => {
    api.listKeys().then(setKeys).catch(() => setKeys([]));
  }, []);

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fd = new FormData(event.currentTarget);
    const issued = await api.createKey({
      label: fd.get('label'),
      scope_libraries: null,
    });
    setRaw(issued.raw);
    setKeys([issued.info, ...keys]);
    setOpen(false);
  }

  async function revoke(id: string) {
    await api.revokeKey(id);
    setKeys(keys.filter(key => key.key_id !== id));
  }

  return (
    <Card
      title={compact ? 'API keys' : 'All my keys'}
      actions={<Button onClick={() => setOpen(true)}>Create key</Button>}
    >
      <Modal open={open} onClose={() => setOpen(false)} title="Create API key">
        <form onSubmit={create} className="space-y-3">
          <input
            name="label"
            required
            placeholder="label"
            className="w-full border rounded px-3 py-2"
          />
          <Button>Create</Button>
        </form>
      </Modal>

      {raw && <pre className="mb-3 bg-slate-100 p-3 rounded">{raw}</pre>}

      <table className="w-full text-sm">
        <tbody>
          {keys.map(key => (
            <tr key={key.key_id} className="border-b">
              <td className="py-2">
                <code>{key.key_id}</code>
              </td>
              <td>{key.label}</td>
              <td>{(key.scope_libraries || []).join(', ') || 'all'}</td>
              <td>
                <Button variant="danger" onClick={() => revoke(key.key_id)}>
                  Revoke
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
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
