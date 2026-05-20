import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { App } from '../src/App';

describe('App',()=>{ beforeEach(()=>{ vi.stubGlobal('fetch', vi.fn(async()=>({ok:true,status:200,text:async()=>JSON.stringify({principal:{principal_id:'anonymous',kind:'anonymous',display_name:'anonymous'},via:'anonymous',libraries:[],roles:[],admin_bypass:false})})) as any); }); it('renders sidebar and anonymous dashboard login', async()=>{ render(<BrowserRouter><App/></BrowserRouter>); await waitFor(()=>expect(screen.getByText('ma3 Knowledge Network')).toBeInTheDocument()); expect(screen.getByText('Login')).toBeInTheDocument(); expect(screen.getByText('Login with auth.zhilicon.com')).toBeInTheDocument(); }); });
