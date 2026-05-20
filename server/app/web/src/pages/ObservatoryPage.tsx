import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { Card } from '../components/ui';
export function ObservatoryPage(){ const [stats,setStats]=useState<any>(); useEffect(()=>{api.overview().then(setStats).catch(()=>setStats({status:'unavailable'}))},[]); return <div className="max-w-5xl mx-auto px-8 py-8"><Card title="Knowledge observatory"><pre className="bg-slate-100 p-3 rounded overflow-auto">{JSON.stringify(stats,null,2)}</pre></Card></div> }
