import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { Card } from '../components/ui';
import { useUser } from '../contexts/UserContext';
export function AdminConsole(){ const { whoami }=useUser(); const [audit,setAudit]=useState<any[]>([]); useEffect(()=>{ if(whoami?.admin_bypass) api.audit().then(setAudit).catch(()=>setAudit([]));},[whoami]); if(!whoami?.admin_bypass) return <div className="max-w-5xl mx-auto px-8 py-8"><Card title="Forbidden">Admin required.</Card></div>; return <div className="max-w-5xl mx-auto px-8 py-8 space-y-6"><Card title="Principals"><p className="text-slate-500">Search and assignment views land here.</p></Card><Card title="Audit"><pre className="bg-slate-100 p-3 rounded text-xs overflow-auto">{JSON.stringify(audit,null,2)}</pre></Card><Card title="Backup"><p className="text-slate-500">Doctor backup block loads from /v2/doctor.</p></Card></div> }
