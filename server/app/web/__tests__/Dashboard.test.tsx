import { describe, it, expect } from 'vitest';
import { screen } from '@testing-library/react';
import { Dashboard } from '../src/pages/Dashboard';
import { renderWithUser } from './test-utils';
describe('Dashboard',()=>{ it('shows effective libraries',()=>{ renderWithUser(<Dashboard/>); expect(screen.getByText('Engineering')).toBeInTheDocument(); expect(screen.getByText('admin')).toBeInTheDocument(); }); });
