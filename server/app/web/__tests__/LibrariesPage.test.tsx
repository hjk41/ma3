import { describe, it, expect } from 'vitest';
import { screen } from '@testing-library/react';
import { LibrariesPage } from '../src/pages/LibrariesPage';
import { renderWithUser } from './test-utils';
describe('LibrariesPage',()=>{ it('renders effective libs and create button',()=>{ renderWithUser(<LibrariesPage/>); expect(screen.getByText('Engineering')).toBeInTheDocument(); expect(screen.getByText('Create library')).toBeInTheDocument(); }); });
