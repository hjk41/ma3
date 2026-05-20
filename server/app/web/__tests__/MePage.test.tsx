import { describe, it, expect, vi } from 'vitest';
import { screen } from '@testing-library/react';
import { MePage } from '../src/pages/MePage';
import { renderWithUser } from './test-utils';
describe('MePage',()=>{ it('renders identity, libraries and keys section',()=>{ vi.stubGlobal('fetch', vi.fn(async()=>({ok:true,status:200,text:async()=>JSON.stringify([])})) as any); renderWithUser(<MePage/>); expect(screen.getByText('user:alice')).toBeInTheDocument(); expect(screen.getByText('library_admin @ lib1')).toBeInTheDocument(); expect(screen.getByText('API keys')).toBeInTheDocument(); }); });
