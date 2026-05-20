import { Card, Badge } from '../components/ui';
import { useUser } from '../contexts/UserContext';
import { KeysPageContent } from './KeysPage';

export function MePage() {
  const { whoami } = useUser();

  if (!whoami) return null;

  return (
    <div className="max-w-5xl mx-auto px-8 py-8 space-y-6">
      <Card title="Identity card">
        <dl className="grid grid-cols-2 gap-3 text-sm">
          <dt className="text-slate-500">Principal</dt>
          <dd>{whoami.principal.principal_id}</dd>
          <dt className="text-slate-500">Kind</dt>
          <dd>{whoami.principal.kind}</dd>
          <dt className="text-slate-500">Via</dt>
          <dd>{whoami.via}</dd>
          <dt className="text-slate-500">Admin bypass</dt>
          <dd>{String(whoami.admin_bypass)}</dd>
        </dl>
      </Card>

      <Card title="Roles list">
        <div className="flex flex-wrap gap-2">
          {(whoami.roles || []).map((role: any) => (
            <Badge
              key={`${role.scope_type}:${role.scope_id}:${role.role_name}`}
              label={`${role.role_name}${role.scope_id ? ` @ ${role.scope_id}` : ''}`}
              color="blue"
            />
          ))}
          {(!whoami.roles || whoami.roles.length === 0) && (
            <span className="text-slate-400">No direct role assignments.</span>
          )}
        </div>
      </Card>

      <Card title="Effective libraries">
        <table className="w-full text-sm">
          <tbody>
            {whoami.libraries.map((library: any) => (
              <tr key={library.library_id} className="border-b">
                <td className="py-2">{library.name || library.library_id}</td>
                <td>
                  <Badge label={library.role} />
                </td>
                <td>{library.source}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <KeysPageContent compact />
    </div>
  );
}
