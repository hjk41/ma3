import { FormEvent, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';
import { Button, Card, Modal, Badge } from '../components/ui';
import { useUser } from '../contexts/UserContext';

export function LibrariesPage() {
  const { whoami, reload } = useUser();
  const [open, setOpen] = useState(false);

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fd = new FormData(event.currentTarget);
    await api.createLibrary({
      name: fd.get('name'),
      description: fd.get('description') || '',
      is_public: Boolean(fd.get('is_public')),
    });
    setOpen(false);
    reload();
  }

  return (
    <div className="max-w-5xl mx-auto px-8 py-8">
      <Card
        title="Libraries"
        actions={<Button onClick={() => setOpen(true)}>Create library</Button>}
      >
        <Modal open={open} onClose={() => setOpen(false)} title="Create library">
          <form onSubmit={create} className="space-y-3">
            <input
              name="name"
              required
              placeholder="name"
              className="w-full border rounded px-3 py-2"
            />
            <input
              name="description"
              placeholder="description"
              className="w-full border rounded px-3 py-2"
            />
            <label className="text-sm">
              <input name="is_public" type="checkbox" /> Public
            </label>
            <Button>Create</Button>
          </form>
        </Modal>

        <div className="grid grid-cols-2 gap-3">
          {whoami?.libraries.map((library: any) => (
            <Link
              key={library.library_id}
              to={`/libs/${library.library_id}`}
              className="border rounded-xl p-4 hover:border-blue-300"
            >
              <div className="font-medium text-slate-800">
                {library.name || library.library_id}
              </div>
              <div className="text-xs text-slate-400">{library.library_id}</div>
              <Badge label={library.role} />
            </Link>
          ))}
        </div>
      </Card>
    </div>
  );
}
