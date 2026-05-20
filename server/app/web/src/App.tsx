import { useEffect, useState } from 'react';
import { Routes, Route } from 'react-router-dom';
import { api, type Whoami } from './api/client';
import { UserContext } from './contexts/UserContext';
import { Sidebar } from './components/Sidebar';
import { Spinner } from './components/ui';
import { Dashboard } from './pages/Dashboard';
import { MePage } from './pages/MePage';
import { LibrariesPage } from './pages/LibrariesPage';
import { LibraryDetail } from './pages/LibraryDetail';
import { KeysPage } from './pages/KeysPage';
import { AdminConsole } from './pages/AdminConsole';
import { ObservatoryPage } from './pages/ObservatoryPage';
import { NotFound } from './pages/NotFound';

export function App() {
  const [whoami, setWhoami] = useState<Whoami | null>(null);
  const [loading, setLoading] = useState(true);
  const [collapsed, setCollapsed] = useState(false);
  const reload = () => { setLoading(true); api.whoami().then(setWhoami).finally(() => setLoading(false)); };
  useEffect(reload, []);
  return <UserContext.Provider value={{ whoami, reload, loading }}><div className="flex min-h-screen bg-slate-50"><Sidebar whoami={whoami} collapsed={collapsed} setCollapsed={setCollapsed}/><main className="flex-1 min-w-0">{loading ? <div className="flex items-center justify-center h-screen"><Spinner/></div> : <Routes><Route path="/" element={<Dashboard/>}/><Route path="/me" element={<MePage/>}/><Route path="/libs" element={<LibrariesPage/>}/><Route path="/libs/:id" element={<LibraryDetail/>}/><Route path="/keys" element={<KeysPage/>}/><Route path="/admin" element={<AdminConsole/>}/><Route path="/observatory" element={<ObservatoryPage/>}/><Route path="*" element={<NotFound/>}/></Routes>}</main></div></UserContext.Provider>;
}
