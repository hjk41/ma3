import { Link } from 'react-router-dom';
import { Card, Badge, Button, Empty, HelpText } from '../components/ui';
import { useUser } from '../contexts/UserContext';
import { buildLoginUrl } from '../auth/loginUrl';

function TaskCard({ to, icon, title, description }: { to: string; icon: string; title: string; description: string }) {
  return (
    <Link
      to={to}
      className="p-4 border border-slate-200 rounded-xl hover:border-blue-300 hover:shadow-sm bg-white transition-all"
    >
      <span className="text-2xl">{icon}</span>
      <span className="block mt-2 text-sm font-semibold text-slate-800">{title}</span>
      <span className="block mt-1 text-xs leading-5 text-slate-500">{description}</span>
    </Link>
  );
}

export function Dashboard() {
  const { whoami } = useUser();
  const anon = !whoami || whoami.principal.kind === 'anonymous';

  return (
    <div className="max-w-5xl mx-auto px-8 py-8">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-slate-800">ma3 Knowledge Network</h1>
        <p className="text-sm text-slate-500 mt-1">
          Verified memories, cases, roles, and API keys for agents.
        </p>
      </div>

      {anon ? (
        <Card title="Welcome to ma3">
          <div className="space-y-4">
            <HelpText>
              ma3 uses auth.zhilicon.com SSO for people and scoped API keys for agents. Sign in to
              manage libraries, issue keys, and inspect role assignments.
            </HelpText>
            <div className="flex flex-wrap gap-2">
              <a href={buildLoginUrl('/')}>
                <Button>Login with auth.zhilicon.com</Button>
              </a>
              <a href="/mcp/info" className="px-4 py-2 rounded-md text-sm font-medium bg-slate-100 text-slate-700 hover:bg-slate-200">
                View MCP endpoint
              </a>
            </div>
          </div>
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-8">
            <TaskCard to="/observatory" icon="🔎" title="Knowledge overview" description="Inspect coverage, search readiness, and MCP-facing context signals." />
            <TaskCard to="/libs" icon="📚" title="Libraries" description="Browse your effective libraries and manage membership." />
            <TaskCard to="/keys" icon="🔑" title="API keys" description="Issue and revoke scoped keys for agents." />
            <TaskCard to="/observatory" icon="🔭" title="Observatory" description="Review record, case, and quality metrics." />
            {whoami?.admin_bypass && (
              <TaskCard to="/admin" icon="🛡️" title="Admin" description="Manage principals, audit logs, backup status, and bulk keys." />
            )}
          </div>

          <Card title="Effective libraries">
            {whoami?.libraries?.length ? (
              <div className="space-y-2">
                {whoami.libraries.map((library: any) => (
                  <Link
                    key={library.library_id}
                    to={`/libs/${library.library_id}`}
                    className="flex items-center justify-between px-3 py-2 rounded hover:bg-slate-50"
                  >
                    <span>
                      <span className="font-medium text-slate-800">{library.name || library.library_id}</span>
                      <code className="ml-2 text-xs text-slate-400">{library.library_id}</code>
                    </span>
                    <Badge
                      label={library.role}
                      color={
                        library.role === 'admin'
                          ? 'blue'
                          : library.role === 'writer'
                            ? 'green'
                            : 'slate'
                      }
                    />
                  </Link>
                ))}
              </div>
            ) : (
              <Empty title="No libraries yet" message="Create or request access to a library before issuing scoped agent keys." />
            )}
          </Card>
        </>
      )}
    </div>
  );
}
