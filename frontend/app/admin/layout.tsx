import React from 'react';

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-gray-900 text-gray-100 flex flex-col" style={{ background: 'var(--bg-default)' }}>
      <header className="p-4 border-b flex justify-between items-center" style={{ background: 'var(--bg-surface)', borderColor: 'var(--border-subtle)' }}>
        <h1 className="text-xl font-bold" style={{ color: 'var(--gold-bright)', fontFamily: 'DM Sans, sans-serif' }}>
          Panel de Administración
        </h1>
      </header>
      <main className="flex-1 p-6">
        {children}
      </main>
    </div>
  );
}
