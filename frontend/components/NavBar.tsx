'use client';

import { useState } from 'react';
import Image from 'next/image';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import * as Dialog from '@radix-ui/react-dialog';
import { Menu, X, MessageSquare, ShieldCheck, LogOut } from 'lucide-react';
import { useAuth } from '@/lib/auth-context';
import { logout } from '@/lib/api';

export default function NavBar() {
  const pathname = usePathname();
  const router = useRouter();
  const [mobileOpen, setMobileOpen] = useState(false);
  const { user, isAdmin, clearAuth } = useAuth();

  const handleLogout = async () => {
    await logout();
    clearAuth();
    router.push('/login');
  };

  const baseLinks = [
    { href: '/chat', label: 'Consultas', icon: MessageSquare },
  ];

  const links = isAdmin
    ? [...baseLinks, { href: '/admin', label: 'Admin', icon: ShieldCheck }]
    : baseLinks;

  // No mostrar navbar en la página de login
  if (!user && pathname === '/login') return null;

  return (
    <nav
      style={{
        background: 'var(--bg-elevated)',
        borderBottom: '1px solid var(--border-gold)',
      }}
      className="shrink-0 px-4 md:px-6 py-0 flex items-center justify-between h-14"
    >
      {/* Logo */}
      <Link href="/chat" className="flex items-center shrink-0">
        <Image
          src="/Banco_Mercantil_Santa_Cruz_Logo.png"
          alt="Banco Mercantil Santa Cruz"
          width={220}
          height={44}
          className="h-8 md:h-9 w-auto object-contain"
          priority
        />
      </Link>

      {/* Desktop links + user */}
      <div className="hidden md:flex items-center gap-2">
        <div
          className="flex items-center gap-1"
          style={{ borderLeft: '1px solid var(--border-subtle)', paddingLeft: '1.5rem', marginLeft: '1.5rem' }}
        >
          {links.map(({ href, label }) => (
            <Link
              key={href}
              href={href}
              className={`nav-link px-4 py-1.5 text-sm rounded-md transition-colors ${
                pathname?.startsWith(href) ? 'active' : ''
              }`}
            >
              {label}
            </Link>
          ))}
        </div>

        {user && (
          <div
            className="flex items-center gap-3 pl-4 ml-2"
            style={{ borderLeft: '1px solid var(--border-subtle)' }}
          >
            <div className="text-right">
              <p className="text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
                {user.username}
              </p>
              <p className="text-xs" style={{ color: 'var(--gold-muted)' }}>
                {user.role?.name ?? 'Sin rol'}
              </p>
            </div>
            <button
              onClick={handleLogout}
              className="p-1.5 rounded-md transition-colors hover:opacity-70"
              style={{ color: 'var(--text-muted)' }}
              title="Cerrar sesión"
            >
              <LogOut size={16} />
            </button>
          </div>
        )}
      </div>

      {/* Mobile hamburger */}
      <Dialog.Root open={mobileOpen} onOpenChange={setMobileOpen}>
        <Dialog.Trigger asChild>
          <button
            className="md:hidden p-2 rounded-md transition-colors"
            style={{ color: 'var(--text-secondary)' }}
            aria-label="Abrir menú"
          >
            <Menu size={20} />
          </button>
        </Dialog.Trigger>

        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 bg-black/70 z-40 md:hidden" />
          <Dialog.Content
            className="fixed left-0 top-0 h-full w-64 z-50 flex flex-col md:hidden"
            style={{ background: 'var(--bg-elevated)', borderRight: '1px solid var(--border-gold)' }}
            aria-describedby={undefined}
          >
            <Dialog.Title className="sr-only">Menú de navegación</Dialog.Title>
            {/* Drawer header */}
            <div
              className="flex items-center justify-between px-4 py-3"
              style={{ borderBottom: '1px solid var(--border-subtle)' }}
            >
              <Image
                src="/LogoBMSC.png"
                alt="MSC"
                width={36}
                height={36}
                className="h-9 w-9 object-contain opacity-80"
              />
              <Dialog.Close asChild>
                <button
                  className="p-1.5 rounded-md"
                  style={{ color: 'var(--text-muted)' }}
                  aria-label="Cerrar menú"
                >
                  <X size={18} />
                </button>
              </Dialog.Close>
            </div>

            {/* Drawer links */}
            <div className="flex flex-col gap-1 p-3 flex-1">
              {links.map(({ href, label, icon: Icon }) => (
                <Dialog.Close asChild key={href}>
                  <Link
                    href={href}
                    className={`flex items-center gap-3 px-4 py-3 rounded-lg text-sm transition-colors`}
                    style={{
                      color: pathname?.startsWith(href) ? 'var(--gold-bright)' : 'var(--text-secondary)',
                      background: pathname?.startsWith(href) ? 'var(--gold-subtle)' : 'transparent',
                    }}
                  >
                    <Icon size={16} />
                    {label}
                  </Link>
                </Dialog.Close>
              ))}
            </div>

            {/* User + logout */}
            {user && (
              <div
                className="px-4 py-3 flex items-center justify-between"
                style={{ borderTop: '1px solid var(--border-subtle)' }}
              >
                <div>
                  <p className="text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
                    {user.username}
                  </p>
                  <p className="text-xs" style={{ color: 'var(--gold-muted)' }}>
                    {user.role?.name ?? 'Sin rol'}
                  </p>
                </div>
                <button
                  onClick={() => { setMobileOpen(false); handleLogout(); }}
                  className="p-1.5 rounded-md"
                  style={{ color: 'var(--text-muted)' }}
                  title="Cerrar sesión"
                >
                  <LogOut size={16} />
                </button>
              </div>
            )}
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </nav>
  );
}
