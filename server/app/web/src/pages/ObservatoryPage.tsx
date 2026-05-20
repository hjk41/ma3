import { useEffect, useMemo, useState } from 'react';
import { api } from '../api/client';
import { Card } from '../components/ui';

function readNumber(source: any, keys: string[]) {
  for (const key of keys) {
    const value = source?.[key];
    if (typeof value === 'number') return value;
  }
  return 0;
}

function percent(value: number, total: number) {
  return total > 0 ? Math.round((value / total) * 100) : 0;
}

export function ObservatoryPage() {
  const [stats, setStats] = useState<any>();

  useEffect(() => {
    api.overview()
      .then(setStats)
      .catch(() => setStats({ status: 'unavailable' }));
  }, []);

  const statusRows = useMemo(() => {
    const distribution = stats?.status_distribution || stats?.by_status || stats?.records_by_status || {};
    return Object.entries(distribution).map(([status, count]) => ({
      status,
      count: Number(count) || 0,
    }));
  }, [stats]);

  const recordsTotal = readNumber(stats, ['records_total', 'record_count', 'records']);
  const casesTotal = readNumber(stats, ['cases_total', 'case_count', 'cases']);
  const librariesTotal = readNumber(stats, ['libraries_total', 'library_count', 'libraries']);
  const drafts = readNumber(stats, ['drafts_total', 'draft_count']);
  const draftPct = stats?.draft_percent ?? percent(drafts, recordsTotal || drafts);
  const maxStatus = Math.max(1, ...statusRows.map(row => row.count));
  const coverage = stats?.case_coverage || {};

  return (
    <div className="max-w-5xl mx-auto px-8 py-8 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">Knowledge observatory</h1>
        <p className="text-sm text-slate-500 mt-1">
          Operational shape of records, cases, libraries, and coverage.
        </p>
      </div>

      <div className="grid grid-cols-4 gap-3">
        <Card title="Records">
          <div className="text-2xl font-bold text-slate-800">{recordsTotal}</div>
          <div className="text-xs text-slate-400">records_total</div>
        </Card>
        <Card title="Cases">
          <div className="text-2xl font-bold text-slate-800">{casesTotal}</div>
          <div className="text-xs text-slate-400">cases_total</div>
        </Card>
        <Card title="Libraries">
          <div className="text-2xl font-bold text-slate-800">{librariesTotal}</div>
          <div className="text-xs text-slate-400">libraries_total</div>
        </Card>
        <Card title="Draft %">
          <div className="text-2xl font-bold text-slate-800">{draftPct}%</div>
          <div className="text-xs text-slate-400">draft records</div>
        </Card>
      </div>

      <Card title="Status distribution">
        {statusRows.length === 0 ? (
          <p className="text-sm text-slate-400">No status distribution available.</p>
        ) : (
          <table className="w-full text-sm">
            <tbody>
              {statusRows.map(row => (
                <tr key={row.status} className="border-b last:border-0">
                  <td className="py-2 w-36 font-medium text-slate-700">{row.status}</td>
                  <td className="py-2 w-20 text-slate-500">{row.count}</td>
                  <td className="py-2">
                    <div className="h-2 rounded bg-slate-100 overflow-hidden">
                      <div
                        className="h-full rounded bg-blue-500"
                        style={{ width: `${percent(row.count, maxStatus)}%` }}
                      />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <Card title="Case coverage">
        <div className="grid grid-cols-3 gap-3 text-sm">
          {Object.entries(coverage).length === 0 ? (
            <p className="text-slate-400">No coverage block available.</p>
          ) : (
            Object.entries(coverage).map(([key, value]) => (
              <div key={key} className="rounded border border-slate-100 p-3">
                <div className="text-xs uppercase tracking-wide text-slate-400">{key}</div>
                <div className="mt-1 text-lg font-semibold text-slate-800">{String(value)}</div>
              </div>
            ))
          )}
        </div>
      </Card>
    </div>
  );
}
