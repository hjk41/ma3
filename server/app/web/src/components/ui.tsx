import { ReactNode } from 'react';

export function Card({ title, children, actions }: { title?: string; children: ReactNode; actions?: ReactNode }) {
  return (
    <div className="bg-white rounded-lg border border-slate-200 shadow-sm">
      {(title || actions) && (
        <div className="flex items-center justify-between px-5 py-3 border-b border-slate-100">
          {title && <h3 className="font-semibold text-slate-800">{title}</h3>}
          {actions && <div className="flex gap-2">{actions}</div>}
        </div>
      )}
      <div className="p-5">{children}</div>
    </div>
  );
}

export function Modal({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: string; children: ReactNode }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div className="bg-white rounded-lg shadow-xl w-full max-w-md mx-4" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-5 py-3 border-b">
          <h3 className="font-semibold">{title}</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 text-xl leading-none">&times;</button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}

export function Badge({ label, color = 'slate' }: { label: string; color?: 'green' | 'red' | 'yellow' | 'slate' | 'blue' }) {
  const colors: Record<string, string> = {
    green: 'bg-green-100 text-green-700',
    red: 'bg-red-100 text-red-700',
    yellow: 'bg-yellow-100 text-yellow-700',
    slate: 'bg-slate-100 text-slate-600',
    blue: 'bg-blue-100 text-blue-700',
  };
  return <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${colors[color]}`}>{label}</span>;
}

export function Spinner() {
  return <div className="flex justify-center py-8"><div className="w-6 h-6 border-2 border-slate-300 border-t-blue-500 rounded-full animate-spin" /></div>;
}

export function Empty({ message }: { message: string }) {
  return <div className="text-center py-12 text-slate-400">{message}</div>;
}

export function ErrorMessage({ message }: { message: string }) {
  return <div className="bg-red-50 border border-red-200 text-red-700 rounded-md p-3 text-sm">{message}</div>;
}

export function Button({ children, variant = 'primary', ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' | 'danger' }) {
  const variants: Record<string, string> = {
    primary: 'bg-blue-600 text-white hover:bg-blue-700',
    secondary: 'bg-slate-100 text-slate-700 hover:bg-slate-200',
    danger: 'bg-red-600 text-white hover:bg-red-700',
  };
  return (
    <button className={`px-4 py-2 rounded-md text-sm font-medium transition-colors disabled:opacity-50 ${variants[variant]}`} {...props}>
      {children}
    </button>
  );
}
