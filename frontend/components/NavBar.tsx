'use client';

import { useState } from 'react';
import Image from 'next/image';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import * as Dialog from '@radix-ui/react-dialog';
import { Menu, X, MessageSquare, BookOpen } from 'lucide-react';

export default function NavBar() {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);

  const links = [
    { href: '/chat', label: 'Consultas', icon: MessageSquare },
    { href: '/documents', label: 'Biblioteca', icon: BookOpen },
  ];

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

      {/* Desktop links */}
      <div
        className="hidden md:flex items-center gap-1"
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
          >
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
                    className={`flex items-center gap-3 px-4 py-3 rounded-lg text-sm transition-colors ${
                      pathname?.startsWith(href) ? 'active' : ''
                    }`}
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

            {/* Drawer footer */}
            <div
              className="px-4 py-3"
              style={{ borderTop: '1px solid var(--border-subtle)' }}
            >
              <p
                className="text-xs"
                style={{ color: 'var(--text-muted)', fontFamily: 'Playfair Display, serif' }}
              >
                Banco Mercantil Santa Cruz
              </p>
              <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
                Asistente Interno · desde 1905
              </p>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </nav>
  );
}
