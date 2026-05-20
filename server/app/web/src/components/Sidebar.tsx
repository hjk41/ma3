import { Link, useLocation } from 'react-router-dom';
import type { Whoami } from '../api/client';
import { buildLoginUrl } from '../auth/loginUrl';

function SidebarLink({ to, active, icon, label, collapsed }: { to: string; active: boolean; icon: string; label: string; collapsed: boolean }) {
  return <Link to={to} className={`flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-slate-800 transition-colors ${active ? 'bg-slate-800 text-white' : ''}`}>{<span className="shrink-0">{icon}</span>}{!collapsed && <span className="truncate">{label}</span>}</Link>;
}

export function Sidebar({ whoami, collapsed, setCollapsed }: { whoami: Whoami | null; collapsed: boolean; setCollapsed: (v: boolean) => void }) {
  const location = useLocation();
  const user = whoami && whoami.principal.kind !== 'anonymous' ? whoami.principal.display_name : '';
  const links = [['/','🏠','Dashboard'], ['/me','👤','Me'], ['/libs','📚','Libraries'], ['/keys','🔑','Keys'], ['/observatory','🔭','Observatory']];
  if (whoami?.admin_bypass) links.push(['/admin','🛡️','Admin']);
  return <aside className={`${collapsed ? 'w-16' : 'w-64'} bg-slate-900 text-slate-300 flex flex-col h-screen sticky top-0 shrink-0 transition-all duration-200`}>
    <div className="flex items-center gap-2 px-4 py-3 border-b border-slate-700"><button onClick={() => setCollapsed(!collapsed)} className="text-slate-400 hover:text-white text-lg shrink-0">{collapsed ? '☰' : '✕'}</button>{!collapsed && <Link to="/" className="font-bold text-white text-sm truncate">ma3</Link>}</div>
    <nav className="flex-1 overflow-y-auto py-2">{links.map(([to, icon, label]) => <SidebarLink key={to} to={to} icon={icon} label={label} collapsed={collapsed} active={location.pathname === to || (to !== '/' && location.pathname.startsWith(to))} />)}</nav>
    <div className="border-t border-slate-700 p-3">{user ? <div className="text-xs"><div className={`flex items-center gap-2 ${collapsed ? 'justify-center' : ''}`}><span className="w-5 h-5 rounded-full bg-green-500 flex items-center justify-center text-[10px] text-white font-bold shrink-0">{user.charAt(0).toUpperCase()}</span>{!collapsed && <span className="truncate">{user}</span>}</div>{!collapsed && <a href="/auth/logout" className="block mt-2 text-red-400 hover:text-red-300">Logout</a>}</div> : <a href={buildLoginUrl()} className={`block text-xs bg-blue-600 hover:bg-blue-500 text-white rounded px-3 py-1.5 w-full ${collapsed ? 'text-center' : ''}`}>{collapsed ? '→' : 'Login'}</a>}</div>
  </aside>;
}
