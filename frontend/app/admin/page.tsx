'use client';

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import * as Dialog from '@radix-ui/react-dialog';
import {
  Users, Shield, FolderOpen, FileText, Plus,
  ChevronDown, ChevronUp, Download, Trash2, Upload,
  CheckCircle2, Circle, Loader2, AlertCircle, RefreshCw, X, UserPlus,
  ArrowRightLeft, RotateCcw, Search, Key, AlertTriangle, Eye, EyeOff, Pencil,
} from 'lucide-react';
import {
  getRoles, createRole, updateRole, deleteRole,
  getUsers, createUser, deactivateUser, activateUser, resetUserPassword, assignUserRole, changeUserEmail, deleteUserPermanent,
  getCollections, createCollection, deleteCollection, CollectionHasDocumentsError,
  getCollectionRolePerms, updateCollectionRolePerm,
  getCollectionUserPerms, updateCollectionUserPerm, deleteCollectionUserPerm,
  getPgDocuments, uploadToCollection, uploadPgDocument, downloadDocument, deletePgDocument,
  updatePgDocument, reactivatePgDocument, permanentDeletePgDocument,
  getDocumentUserPerms, updateDocumentUserPerm, deleteDocumentUserPerm,
} from '@/lib/api';
import type {
  RoleInfo, UserOut, CollectionOut, RolePermEntry, UserPermEntry, PgDocumentOut, DocUserPermEntry,
  PgDocumentsFilters,
} from '@/lib/api';
import { useAuth } from '@/lib/auth-context';
import ConfirmModal from '@/components/ui/ConfirmModal';

// Roles asignables a colecciones: excluye SUPERADMIN y ADMIN (siempre tienen
// acceso total por sus permisos globales); deja VISITANTE + cualquier custom.
const ROLE_NAMES_HIDDEN_IN_COLLECTIONS = new Set(['SUPERADMIN', 'ADMIN']);
function selectableCollectionRoles(roles: RoleInfo[]): RoleInfo[] {
  return roles.filter((r) => !ROLE_NAMES_HIDDEN_IN_COLLECTIONS.has(r.name));
}

// ── helpers ────────────────────────────────────────────────────────────────

function initials(name: string) {
  return name.slice(0, 2).toUpperCase();
}

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('es-BO', {
    day: '2-digit', month: 'short', year: 'numeric',
  });
}

const RAG_LABEL: Record<string, { label: string; color: string; icon: React.ReactNode }> = {
  pending:         { label: 'Pendiente',   color: '#A67B2A', icon: <Circle size={11} /> },
  indexing_images: { label: 'Procesando',  color: '#2563EB', icon: <Loader2 size={11} className="animate-spin" /> },
  ready:           { label: 'Listo',       color: '#2D7A4F', icon: <CheckCircle2 size={11} /> },
  error:           { label: 'Error',       color: '#8B2233', icon: <AlertCircle size={11} /> },
  sin_rag:         { label: 'Sin RAG',     color: '#4A6B58', icon: <Circle size={11} /> },
};

type PermKey = 'can_manage_users' | 'can_manage_collections' | 'can_upload_documents' | 'can_delete_documents';

const PERM_LABELS: { key: PermKey; label: string }[] = [
  { key: 'can_manage_users',        label: 'Gestionar usuarios' },
  { key: 'can_manage_collections',  label: 'Gestionar colecciones' },
  { key: 'can_upload_documents',    label: 'Subir documentos' },
  { key: 'can_delete_documents',    label: 'Eliminar documentos' },
];

// ── sub-components ─────────────────────────────────────────────────────────

function NavItem({
  id, label, icon: Icon, active, onClick,
}: { id: string; label: string; icon: React.ElementType; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="w-full flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-medium transition-all"
      style={{
        background: active ? 'var(--gold-subtle)' : 'transparent',
        color: active ? 'var(--gold-bright)' : 'var(--text-secondary)',
        borderLeft: active ? '2px solid var(--gold-bright)' : '2px solid transparent',
      }}
    >
      <Icon size={16} />
      {label}
    </button>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2
      className="text-lg font-semibold mb-5"
      style={{ color: 'var(--gold-bright)', fontFamily: 'Playfair Display, serif' }}
    >
      {children}
    </h2>
  );
}

function StatusBadge({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span
      className="text-xs px-2 py-0.5 rounded-full"
      style={{
        background: ok ? 'rgba(45,122,79,0.2)' : 'rgba(100,100,100,0.15)',
        color: ok ? '#4ade80' : '#6b7280',
      }}
    >
      {label}
    </span>
  );
}

function Card({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <div
      className={`rounded-xl border p-5 ${className}`}
      style={{ background: 'var(--bg-surface)', borderColor: 'var(--border-subtle)' }}
    >
      {children}
    </div>
  );
}

function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={`w-full px-3 py-2 rounded-lg border text-sm transition-colors focus:outline-none focus:ring-1 focus:ring-yellow-600 ${props.className ?? ''}`}
      style={{ background: 'var(--bg-elevated)', borderColor: 'var(--border-default)', color: 'var(--text-primary)', ...props.style }}
    />
  );
}

function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...props}
      className={`w-full px-3 py-2 rounded-lg border text-sm focus:outline-none focus:ring-1 focus:ring-yellow-600 ${props.className ?? ''}`}
      style={{ background: 'var(--bg-elevated)', borderColor: 'var(--border-default)', color: 'var(--text-primary)', ...props.style }}
    />
  );
}

function BtnPrimary({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...props}
      className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 ${props.className ?? ''}`}
      style={{ background: 'var(--gold-muted)', color: 'var(--bg-base)', ...props.style }}
      onMouseEnter={(e) => { if (!props.disabled) e.currentTarget.style.background = 'var(--gold-bright)'; }}
      onMouseLeave={(e) => { e.currentTarget.style.background = 'var(--gold-muted)'; }}
    >
      {children}
    </button>
  );
}

function BtnGhost({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...props}
      className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors disabled:opacity-50 ${props.className ?? ''}`}
      style={{ borderColor: 'var(--border-default)', color: 'var(--text-secondary)', background: 'transparent', ...props.style }}
    >
      {children}
    </button>
  );
}

function Toast({ msg, type }: { msg: string; type: 'ok' | 'err' }) {
  return (
    <div
      className="fixed bottom-6 right-6 px-5 py-3 rounded-xl text-sm font-medium shadow-xl z-50 animate-slide-up"
      style={{
        background: type === 'ok' ? 'var(--bg-elevated)' : '#3f0a14',
        color: type === 'ok' ? 'var(--gold-bright)' : '#f87171',
        border: `1px solid ${type === 'ok' ? 'var(--border-gold)' : '#7f1d1d'}`,
      }}
    >
      {msg}
    </div>
  );
}

// ── SECTION: Usuarios ──────────────────────────────────────────────────────

function ResetPasswordModal({
  user, onClose, onDone, flash,
}: {
  user: UserOut;
  onClose: () => void;
  onDone: () => void;
  flash: (msg: string, type?: 'ok' | 'err') => void;
}) {
  const [pw, setPw] = useState('');
  const [pw2, setPw2] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [showPw2, setShowPw2] = useState(false);
  const [busy, setBusy] = useState(false);
  const valid = pw.length >= 4 && pw === pw2;

  const save = async () => {
    if (!valid) return;
    setBusy(true);
    try {
      await resetUserPassword(user.id, pw);
      flash(`Contraseña temporal actualizada para ${user.username}. Deberá cambiarla al iniciar sesión.`);
      onDone();
      onClose();
    } catch (err) {
      flash(err instanceof Error ? err.message : 'Error', 'err');
    }
    setBusy(false);
  };

  return (
    <Dialog.Root open onOpenChange={(o) => { if (!o && !busy) onClose(); }}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm" />
        <Dialog.Content
          className="fixed z-50 top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-full max-w-md rounded-2xl p-6 shadow-2xl max-h-[90vh] overflow-y-auto"
          style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-default)' }}
        >
          <Dialog.Title
            className="text-base font-semibold mb-2"
            style={{ color: 'var(--gold-bright)', fontFamily: 'Playfair Display, serif' }}
          >
            Cambiar contraseña
          </Dialog.Title>
          <Dialog.Description className="text-sm mb-3" style={{ color: 'var(--text-secondary)' }}>
            Contraseña temporal para <strong>{user.username}</strong>. Esto cerrará sus sesiones activas y obligará cambio en el próximo ingreso.
          </Dialog.Description>
          <div className="space-y-2">
            <div className="relative">
              <Input type={showPw ? 'text' : 'password'} placeholder="Nueva contraseña" value={pw}
                onChange={(e) => setPw(e.target.value)} autoFocus style={{ paddingRight: 36 }} />
              <button type="button" tabIndex={-1} onClick={() => setShowPw(v => !v)}
                className="absolute right-2 top-1/2 -translate-y-1/2" style={{ color: 'var(--text-muted)' }}>
                {showPw ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </div>
            <div className="relative">
              <Input type={showPw2 ? 'text' : 'password'} placeholder="Repetir contraseña" value={pw2}
                onChange={(e) => setPw2(e.target.value)} style={{ paddingRight: 36 }} />
              <button type="button" tabIndex={-1} onClick={() => setShowPw2(v => !v)}
                className="absolute right-2 top-1/2 -translate-y-1/2" style={{ color: 'var(--text-muted)' }}>
                {showPw2 ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </div>
            {pw && pw2 && pw !== pw2 && (
              <p className="text-xs" style={{ color: '#f87171' }}>Las contraseñas no coinciden</p>
            )}
            {pw && pw.length < 4 && (
              <p className="text-xs" style={{ color: '#f87171' }}>Mínimo 4 caracteres</p>
            )}
          </div>
          <div className="flex justify-end gap-2 mt-5">
            <button
              disabled={busy}
              onClick={onClose}
              className="px-4 py-2 rounded-lg text-xs font-medium disabled:opacity-50"
              style={{ color: 'var(--text-secondary)', border: '1px solid var(--border-default)', background: 'var(--bg-surface)' }}
            >Cancelar</button>
            <button
              disabled={busy || !valid}
              onClick={save}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold disabled:opacity-50"
              style={{ background: 'var(--gold-bright)', color: '#0A1A10' }}
            >
              {busy && <Loader2 size={12} className="animate-spin" />}
              Guardar contraseña temporal
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function AssignRoleModal({
  user, roles, onClose, onDone, flash,
}: {
  user: UserOut;
  roles: RoleInfo[];
  onClose: () => void;
  onDone: () => void;
  flash: (msg: string, type?: 'ok' | 'err') => void;
}) {
  const [roleId, setRoleId] = useState<string>(user.role_id ?? '');
  const [busy, setBusy] = useState(false);

  const save = async () => {
    if (!roleId) return;
    setBusy(true);
    try {
      await assignUserRole(user.id, roleId);
      flash(`Rol asignado a ${user.username}`);
      onDone();
      onClose();
    } catch (err) {
      flash(err instanceof Error ? err.message : 'Error', 'err');
    }
    setBusy(false);
  };

  return (
    <Dialog.Root open onOpenChange={(o) => { if (!o && !busy) onClose(); }}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm" />
        <Dialog.Content
          className="fixed z-50 top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-full max-w-md rounded-2xl p-6 shadow-2xl max-h-[90vh] overflow-y-auto"
          style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-default)' }}
        >
          <Dialog.Title
            className="text-base font-semibold mb-2"
            style={{ color: 'var(--gold-bright)', fontFamily: 'Playfair Display, serif' }}
          >
            Asignar rol
          </Dialog.Title>
          <Dialog.Description className="text-sm mb-3" style={{ color: 'var(--text-secondary)' }}>
            Asignar un rol a <strong>{user.username}</strong>.
            {!user.role_id && <span> Sin rol no puede iniciar sesión.</span>}
          </Dialog.Description>
          <Select value={roleId} onChange={(e) => setRoleId(e.target.value)}>
            <option value="">Seleccionar rol</option>
            {roles.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
          </Select>
          <div className="flex justify-end gap-2 mt-5">
            <button
              disabled={busy}
              onClick={onClose}
              className="px-4 py-2 rounded-lg text-xs font-medium disabled:opacity-50"
              style={{ color: 'var(--text-secondary)', border: '1px solid var(--border-default)', background: 'var(--bg-surface)' }}
            >Cancelar</button>
            <button
              disabled={busy || !roleId}
              onClick={save}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold disabled:opacity-50"
              style={{ background: 'var(--gold-bright)', color: '#0A1A10' }}
            >
              {busy && <Loader2 size={12} className="animate-spin" />}
              Asignar
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function ChangeEmailModal({
  user, onClose, onDone, flash,
}: {
  user: UserOut;
  onClose: () => void;
  onDone: () => void;
  flash: (msg: string, type?: 'ok' | 'err') => void;
}) {
  const [email, setEmail] = useState(user.email ?? '');
  const [busy, setBusy] = useState(false);
  const trimmed = email.trim().toLowerCase();
  const valid = trimmed.length >= 3 && trimmed.includes('@') && trimmed !== (user.email ?? '').toLowerCase();

  const save = async () => {
    if (!valid) return;
    setBusy(true);
    try {
      await changeUserEmail(user.id, trimmed);
      flash(`Correo actualizado. El usuario ahora inicia sesión con "${trimmed}"`);
      onDone();
      onClose();
    } catch (err) {
      flash(err instanceof Error ? err.message : 'Error', 'err');
    }
    setBusy(false);
  };

  return (
    <Dialog.Root open onOpenChange={(o) => { if (!o && !busy) onClose(); }}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm" />
        <Dialog.Content
          className="fixed z-50 top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-full max-w-md rounded-2xl p-6 shadow-2xl max-h-[90vh] overflow-y-auto"
          style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-default)' }}
        >
          <Dialog.Title
            className="text-base font-semibold mb-2"
            style={{ color: 'var(--gold-bright)', fontFamily: 'Playfair Display, serif' }}
          >
            Cambiar correo
          </Dialog.Title>
          <Dialog.Description className="text-sm mb-3" style={{ color: 'var(--text-secondary)' }}>
            Nuevo correo de acceso para <strong>{user.username}</strong>. El nombre visible se actualizará automáticamente.
          </Dialog.Description>
          <Input
            type="email"
            placeholder="nuevo@bmsc.com.bo"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoFocus
          />
          <div className="flex justify-end gap-2 mt-5">
            <button
              disabled={busy}
              onClick={onClose}
              className="px-4 py-2 rounded-lg text-xs font-medium disabled:opacity-50"
              style={{ color: 'var(--text-secondary)', border: '1px solid var(--border-default)', background: 'var(--bg-surface)' }}
            >Cancelar</button>
            <button
              disabled={busy || !valid}
              onClick={save}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold disabled:opacity-50"
              style={{ background: 'var(--gold-bright)', color: '#0A1A10' }}
            >
              {busy && <Loader2 size={12} className="animate-spin" />}
              Guardar
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function PermanentDeleteUserModal({
  user, onClose, onDone, flash,
}: {
  user: UserOut;
  onClose: () => void;
  onDone: () => void;
  flash: (msg: string, type?: 'ok' | 'err') => void;
}) {
  const [typed, setTyped] = useState('');
  const [busy, setBusy] = useState(false);
  const expected = user.username;
  const matches = typed.trim() === expected;

  const doPurge = async () => {
    if (!matches) return;
    setBusy(true);
    try {
      await deleteUserPermanent(user.id);
      flash('Usuario eliminado permanentemente');
      onDone();
      onClose();
    } catch (err) {
      flash(err instanceof Error ? err.message : 'Error', 'err');
    }
    setBusy(false);
  };

  return (
    <Dialog.Root open onOpenChange={(o) => { if (!o && !busy) onClose(); }}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm" />
        <Dialog.Content
          className="fixed z-50 top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-full max-w-md rounded-2xl p-6 shadow-2xl max-h-[90vh] overflow-y-auto"
          style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-default)' }}
        >
          <div className="flex items-center gap-2 mb-2">
            <AlertTriangle size={18} style={{ color: '#f87171' }} />
            <Dialog.Title
              className="text-base font-semibold"
              style={{ color: '#f87171', fontFamily: 'Playfair Display, serif' }}
            >
              Eliminar usuario permanentemente
            </Dialog.Title>
          </div>
          <Dialog.Description className="text-sm mb-3" style={{ color: 'var(--text-secondary)' }}>
            Esta acción borra la cuenta, sus permisos y todas sus conversaciones.
            Los documentos y colecciones que creó se conservan, pero quedan sin creador asignado.{' '}
            <strong>No se puede deshacer.</strong>
          </Dialog.Description>
          <p className="text-xs mb-2" style={{ color: 'var(--text-muted)' }}>
            Escriba el nombre del usuario para confirmar:
          </p>
          <p className="text-xs mb-2 font-mono px-2 py-1 rounded" style={{ background: 'var(--bg-base)', color: 'var(--text-primary)' }}>
            {expected}
          </p>
          <Input value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="Nombre del usuario..." />
          <div className="flex justify-end gap-2 mt-5">
            <button
              disabled={busy}
              onClick={onClose}
              className="px-4 py-2 rounded-lg text-xs font-medium disabled:opacity-50"
              style={{ color: 'var(--text-secondary)', border: '1px solid var(--border-default)', background: 'var(--bg-surface)' }}
            >Cancelar</button>
            <button
              disabled={busy || !matches}
              onClick={doPurge}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold disabled:opacity-50"
              style={{ background: '#7f1d1d', color: '#fee2e2' }}
            >
              {busy && <Loader2 size={12} className="animate-spin" />}
              Eliminar para siempre
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function UsuariosSection({ roles }: { roles: RoleInfo[] }) {
  const [users, setUsers] = useState<UserOut[]>([]);
  const [form, setForm] = useState({ email: '', password: '', role_id: '' });
  const [confirmPw, setConfirmPw] = useState('');
  const [manualPassword, setManualPassword] = useState(false);
  const [showPw, setShowPw] = useState(false);
  const [showConfirmPw, setShowConfirmPw] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ text: string; type: 'ok' | 'err' } | null>(null);
  const [confirmDeactivate, setConfirmDeactivate] = useState<{ id: string; username: string } | null>(null);
  const [resetPwUser, setResetPwUser] = useState<UserOut | null>(null);
  const [assignRoleUser, setAssignRoleUser] = useState<UserOut | null>(null);
  const [changeEmailUser, setChangeEmailUser] = useState<UserOut | null>(null);
  const [permanentDeleteUser, setPermanentDeleteUser] = useState<UserOut | null>(null);
  const [actionBusy, setActionBusy] = useState<string | null>(null);

  // Filter state
  const [userSearch, setUserSearch] = useState('');
  const [userSearchD, setUserSearchD] = useState('');
  const [userStatusFilter, setUserStatusFilter] = useState<'' | 'active' | 'inactive'>('');
  const [userRoleFilter, setUserRoleFilter] = useState<'' | '__none__' | string>('');
  const [userSort, setUserSort] = useState<'newest' | 'oldest' | 'az'>('newest');

  const flash = useCallback((text: string, type: 'ok' | 'err' = 'ok') => {
    setMsg({ text, type });
    setTimeout(() => setMsg(null), 3000);
  }, []);

  const load = useCallback(async () => {
    try { const r = await getUsers(); setUsers(r.items); } catch {}
  }, []);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    const t = setTimeout(() => setUserSearchD(userSearch), 250);
    return () => clearTimeout(t);
  }, [userSearch]);

  const passwordTrimmed = form.password.trim();
  const passwordProvided = manualPassword && passwordTrimmed.length > 0;
  const passwordsValid = !manualPassword || (form.password.length >= 4 && form.password === confirmPw);
  const emailValid = form.email.trim().includes('@') && form.email.trim().length >= 3;

  const toggleManualPassword = () => {
    setManualPassword((current) => {
      const next = !current;
      if (!next) {
        setForm((value) => ({ ...value, password: '' }));
        setConfirmPw('');
        setShowPw(false);
        setShowConfirmPw(false);
      }
      return next;
    });
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!passwordsValid || !emailValid) return;
    setBusy(true);
    try {
      await createUser({
        email: form.email.trim().toLowerCase(),
        ...(passwordProvided ? { password: form.password } : {}),
        role_id: form.role_id,
      });
      setForm({ email: '', password: '', role_id: '' });
      setManualPassword(false);
      setConfirmPw(''); setShowPw(false); setShowConfirmPw(false);
      await load();
      flash('Usuario creado correctamente');
    } catch (err) { flash(err instanceof Error ? err.message : 'Error', 'err'); }
    setBusy(false);
  };

  const doDeactivate = async () => {
    if (!confirmDeactivate) return;
    try {
      await deactivateUser(confirmDeactivate.id);
      await load();
      flash('Usuario desactivado');
    } catch (err) { flash(err instanceof Error ? err.message : 'Error', 'err'); }
    setConfirmDeactivate(null);
  };

  const handleActivate = async (u: UserOut) => {
    setActionBusy(u.id);
    try {
      await activateUser(u.id);
      await load();
      flash(`Usuario ${u.username} reactivado`);
    } catch (err) { flash(err instanceof Error ? err.message : 'Error', 'err'); }
    setActionBusy(null);
  };

  const filteredUsers = useMemo(() => {
    let r = [...users];
    if (userSearchD.trim()) {
      const q = userSearchD.toLowerCase();
      r = r.filter(u => u.username.toLowerCase().includes(q) || (u.email ?? '').toLowerCase().includes(q));
    }
    if (userStatusFilter === 'active')   r = r.filter(u => u.is_active);
    if (userStatusFilter === 'inactive') r = r.filter(u => !u.is_active);
    if (userRoleFilter === '__none__')   r = r.filter(u => !u.role_id);
    else if (userRoleFilter)             r = r.filter(u => u.role_id === userRoleFilter);
    if (userSort === 'newest') r.sort((a, b) => b.created_at.localeCompare(a.created_at));
    if (userSort === 'oldest') r.sort((a, b) => a.created_at.localeCompare(b.created_at));
    if (userSort === 'az')     r.sort((a, b) => a.username.localeCompare(b.username));
    return r;
  }, [users, userSearchD, userStatusFilter, userRoleFilter, userSort]);

  const anyUserFilter = userSearch !== '' || userStatusFilter !== '' || userRoleFilter !== '' || userSort !== 'newest';

  return (
    <div className="space-y-6">
      {msg && <Toast msg={msg.text} type={msg.type} />}
      {resetPwUser && (
        <ResetPasswordModal user={resetPwUser} onClose={() => setResetPwUser(null)} onDone={load} flash={flash} />
      )}
      {assignRoleUser && (
        <AssignRoleModal user={assignRoleUser} roles={roles} onClose={() => setAssignRoleUser(null)} onDone={load} flash={flash} />
      )}
      {changeEmailUser && (
        <ChangeEmailModal user={changeEmailUser} onClose={() => setChangeEmailUser(null)} onDone={load} flash={flash} />
      )}
      {permanentDeleteUser && (
        <PermanentDeleteUserModal user={permanentDeleteUser} onClose={() => setPermanentDeleteUser(null)} onDone={load} flash={flash} />
      )}
      <ConfirmModal
        open={!!confirmDeactivate}
        onOpenChange={(o) => { if (!o) setConfirmDeactivate(null); }}
        title="Desactivar usuario"
        description={`¿Desactivar al usuario "${confirmDeactivate?.username}"? No podrá iniciar sesión hasta que sea reactivado.`}
        confirmLabel="Desactivar"
        destructive
        onConfirm={doDeactivate}
      />
      <Card>
        <SectionTitle>Registrar Usuario</SectionTitle>
        <form onSubmit={handleCreate} className="grid grid-cols-1 gap-3 max-w-md">
          <Input
            type="email" placeholder="correo@bmsc.com.bo" required
            value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })}
          />
          <div className="flex items-center justify-between gap-3 rounded-lg border px-3 py-2" style={{ background: 'var(--bg-elevated)', borderColor: 'var(--border-default)' }}>
            <div className="min-w-0">
              <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>Definir contraseña temporal</p>
              <p className="text-xs" style={{ color: 'var(--text-muted)' }}>Apagado: el sistema la genera y la envía por correo.</p>
            </div>
            <button
              type="button"
              role="switch"
              aria-checked={manualPassword}
              aria-label="Definir contraseña temporal manualmente"
              onClick={toggleManualPassword}
              style={{
                width: 40, height: 22, borderRadius: 999,
                background: manualPassword ? 'var(--gold-muted)' : 'var(--bg-base)',
                border: `1px solid ${manualPassword ? 'var(--gold-bright)' : 'var(--border-default)'}`,
                position: 'relative', cursor: 'pointer', flexShrink: 0,
                transition: 'background 0.15s, border-color 0.15s',
              }}
            >
              <span
                style={{
                  position: 'absolute', top: 3,
                  left: manualPassword ? 20 : 3, width: 14, height: 14,
                  borderRadius: '50%',
                  background: manualPassword ? 'var(--gold-bright)' : 'var(--text-muted)',
                  transition: 'left 0.15s, background 0.15s',
                }}
              />
            </button>
          </div>
          {manualPassword && (
            <>
              <div className="relative">
                <Input
                  type={showPw ? 'text' : 'password'} placeholder="Contraseña temporal"
                  value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })}
                  style={{ paddingRight: 36 }}
                />
                <button type="button" tabIndex={-1} onClick={() => setShowPw(v => !v)}
                  className="absolute right-2 top-1/2 -translate-y-1/2" style={{ color: 'var(--text-muted)' }}>
                  {showPw ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
              </div>
              <div className="relative">
                <Input
                  type={showConfirmPw ? 'text' : 'password'} placeholder="Repetir contraseña"
                  value={confirmPw} onChange={(e) => setConfirmPw(e.target.value)}
                  style={{ paddingRight: 36 }}
                />
                <button type="button" tabIndex={-1} onClick={() => setShowConfirmPw(v => !v)}
                  className="absolute right-2 top-1/2 -translate-y-1/2" style={{ color: 'var(--text-muted)' }}>
                  {showConfirmPw ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
              </div>
              {form.password && form.password.length < 4 && (
                <p className="text-xs" style={{ color: '#f87171' }}>Mínimo 4 caracteres</p>
              )}
              {passwordProvided && confirmPw && form.password !== confirmPw && (
                <p className="text-xs" style={{ color: '#f87171' }}>Las contraseñas no coinciden</p>
              )}
            </>
          )}
          <Select required value={form.role_id} onChange={(e) => setForm({ ...form, role_id: e.target.value })}>
            <option value="">Seleccionar rol</option>
            {roles.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
          </Select>
          <BtnPrimary type="submit" disabled={busy || !passwordsValid || !emailValid}>
            <Plus size={14} /> {busy ? 'Creando...' : 'Crear Usuario'}
          </BtnPrimary>
        </form>
      </Card>

      <Card>
        <div className="flex items-center justify-between mb-4">
          <SectionTitle>Usuarios Registrados</SectionTitle>
          <BtnGhost onClick={load}><RefreshCw size={12} /> Actualizar</BtnGhost>
        </div>
        <div className="flex items-center gap-2 mb-3 flex-wrap">
          <div className="relative flex-1 min-w-[180px]">
            <Search size={12} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--text-muted)' }} />
            <Input type="text" placeholder="Buscar por nombre o correo..." value={userSearch}
              onChange={(e) => setUserSearch(e.target.value)} style={{ paddingLeft: 30 }} />
          </div>
          <Select value={userStatusFilter} onChange={(e) => setUserStatusFilter(e.target.value as '' | 'active' | 'inactive')} className="text-xs w-36">
            <option value="">Todos</option>
            <option value="active">Activos</option>
            <option value="inactive">Inactivos</option>
          </Select>
          <Select value={userRoleFilter} onChange={(e) => setUserRoleFilter(e.target.value)} className="text-xs w-44">
            <option value="">Todos los roles</option>
            <option value="__none__">Sin rol</option>
            {roles.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
          </Select>
          <Select value={userSort} onChange={(e) => setUserSort(e.target.value as 'newest' | 'oldest' | 'az')} className="text-xs w-44">
            <option value="newest">Más recientes</option>
            <option value="oldest">Más antiguos</option>
            <option value="az">Nombre A-Z</option>
          </Select>
          {anyUserFilter && (
            <BtnGhost onClick={() => { setUserSearch(''); setUserStatusFilter(''); setUserRoleFilter(''); setUserSort('newest'); }}>
              <X size={12} /> Limpiar filtros
            </BtnGhost>
          )}
        </div>
        <p className="text-xs mb-2" style={{ color: 'var(--text-muted)' }}>{filteredUsers.length} de {users.length} usuarios</p>
        <div className="space-y-2">
          {users.length === 0 && (
            <p className="text-sm" style={{ color: 'var(--text-muted)' }}>No hay usuarios.</p>
          )}
          {users.length > 0 && filteredUsers.length === 0 && (
            <p className="text-sm" style={{ color: 'var(--text-muted)' }}>No se encontraron usuarios con los filtros aplicados.</p>
          )}
          {filteredUsers.map((u) => {
            const noRole = !u.role_id;
            return (
              <div
                key={u.id}
                className="flex items-center justify-between px-4 py-3 rounded-lg flex-wrap gap-2"
                style={{ background: 'var(--bg-elevated)' }}
              >
                <div className="flex items-center gap-3">
                  <div
                    className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold"
                    style={{ background: 'var(--gold-subtle)', color: 'var(--gold-bright)' }}
                  >
                    {initials(u.username)}
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{u.username}</p>
                      {u.is_system && (
                        <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: 'rgba(234,179,8,0.15)', color: '#fbbf24' }}>
                          sistema
                        </span>
                      )}
                    </div>
                    {u.email && (
                      <p className="text-xs" style={{ color: 'var(--text-muted)', fontFamily: 'DM Sans, sans-serif' }}>{u.email}</p>
                    )}
                    {noRole ? (
                      <span
                        className="inline-flex items-center gap-1 text-xs px-1.5 py-0.5 rounded mt-0.5 border"
                        style={{ background: 'rgba(245, 158, 11, 0.15)', color: '#fbbf24', borderColor: 'rgba(245, 158, 11, 0.4)' }}
                      >
                        <AlertTriangle size={10} /> Sin rol
                      </span>
                    ) : (
                      <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>{u.role?.name}</p>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                  <StatusBadge ok={u.is_active} label={u.is_active ? 'activo' : 'inactivo'} />
                  {noRole && !u.is_system && (
                    <button
                      onClick={() => setAssignRoleUser(u)}
                      className="text-xs px-2 py-1 rounded border transition-colors"
                      style={{ borderColor: 'rgba(245, 158, 11, 0.5)', color: '#fbbf24' }}
                    >
                      Asignar rol
                    </button>
                  )}
                  {!noRole && !u.is_system && (
                    <button
                      onClick={() => setAssignRoleUser(u)}
                      className="text-xs px-2 py-1 rounded border transition-colors"
                      style={{ borderColor: 'var(--border-default)', color: 'var(--text-secondary)' }}
                    >
                      Cambiar rol
                    </button>
                  )}
                  <button
                    onClick={() => setResetPwUser(u)}
                    className="flex items-center gap-1 text-xs px-2 py-1 rounded border transition-colors"
                    style={{ borderColor: 'var(--border-default)', color: 'var(--text-secondary)' }}
                    title="Restablecer contraseña"
                  >
                    <Key size={11} /> Contraseña
                  </button>
                  {!u.is_system && (
                    <button
                      onClick={() => setChangeEmailUser(u)}
                      className="flex items-center gap-1 text-xs px-2 py-1 rounded border transition-colors"
                      style={{ borderColor: 'var(--border-default)', color: 'var(--text-secondary)' }}
                      title="Cambiar correo de acceso"
                    >
                      <Pencil size={11} /> Correo
                    </button>
                  )}
                  {!u.is_system && (
                    u.is_active ? (
                      <button
                        onClick={() => setConfirmDeactivate({ id: u.id, username: u.username })}
                        className="text-xs px-2 py-1 rounded border transition-colors"
                        style={{ borderColor: 'var(--status-red)', color: '#f87171' }}
                      >
                        Desactivar
                      </button>
                    ) : (
                      <button
                        onClick={() => handleActivate(u)}
                        disabled={actionBusy === u.id}
                        className="flex items-center gap-1 text-xs px-2 py-1 rounded border transition-colors disabled:opacity-50"
                        style={{ borderColor: '#2D7A4F', color: '#4ade80' }}
                      >
                        {actionBusy === u.id
                          ? <Loader2 size={11} className="animate-spin" />
                          : <RotateCcw size={11} />}
                        Reactivar
                      </button>
                    )
                  )}
                  {!u.is_system && !u.is_active && (
                    <button
                      onClick={() => setPermanentDeleteUser(u)}
                      className="flex items-center gap-1 text-xs px-2 py-1 rounded border transition-colors"
                      style={{ borderColor: '#7f1d1d', color: '#f87171' }}
                      title="Eliminar permanentemente"
                    >
                      <Trash2 size={11} /> Eliminar
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </Card>
    </div>
  );
}

// ── SECTION: Roles ─────────────────────────────────────────────────────────

type RolePerms = {
  can_manage_users: boolean;
  can_manage_collections: boolean;
  can_upload_documents: boolean;
  can_delete_documents: boolean;
};

function RoleCard({
  role,
  onSaved,
  onDeleted,
  flash,
}: {
  role: RoleInfo;
  onSaved: () => void;
  onDeleted: () => void;
  flash: (msg: string, type?: 'ok' | 'err') => void;
}) {
  const [editing, setEditing] = useState(false);
  const [perms, setPerms] = useState<RolePerms>({
    can_manage_users: role.can_manage_users,
    can_manage_collections: role.can_manage_collections,
    can_upload_documents: role.can_upload_documents,
    can_delete_documents: role.can_delete_documents,
  });
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const handleSave = async () => {
    setBusy(true);
    try {
      await updateRole(role.id, perms);
      onSaved();
      setEditing(false);
      flash('Permisos del rol actualizados');
    } catch (err) {
      flash(err instanceof Error ? err.message : 'Error al actualizar', 'err');
    }
    setBusy(false);
  };

  const doDelete = async () => {
    try {
      await deleteRole(role.id);
      onDeleted();
      flash('Rol eliminado');
    } catch (err) { flash(err instanceof Error ? err.message : 'Error', 'err'); }
    setConfirmDelete(false);
  };

  return (
    <>
      <ConfirmModal
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title="Eliminar rol"
        description={`¿Eliminar el rol "${role.name}"? Esta acción no se puede deshacer y afectará a todos los usuarios con este rol.`}
        confirmLabel="Eliminar"
        destructive
        onConfirm={doDelete}
      />
      <div className="rounded-lg overflow-hidden" style={{ background: 'var(--bg-elevated)' }}>
        {/* Header row */}
        <div className="flex items-center justify-between px-4 py-3">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>{role.name}</span>
            {role.is_system && (
              <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: 'rgba(234,179,8,0.15)', color: '#fbbf24' }}>sistema</span>
            )}
            {role.description && (
              <span className="text-xs" style={{ color: 'var(--text-muted)' }}>— {role.description}</span>
            )}
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {!role.is_system && (!editing ? (
              <BtnGhost onClick={() => setEditing(true)}>Editar permisos</BtnGhost>
            ) : (
              <>
                <BtnGhost onClick={() => { setEditing(false); setPerms({ can_manage_users: role.can_manage_users, can_manage_collections: role.can_manage_collections, can_upload_documents: role.can_upload_documents, can_delete_documents: role.can_delete_documents }); }}>
                  Cancelar
                </BtnGhost>
                <BtnPrimary onClick={handleSave} disabled={busy}>
                  {busy ? 'Guardando...' : 'Guardar'}
                </BtnPrimary>
              </>
            ))}
            {!role.is_system && !editing && (
              <button
                onClick={() => setConfirmDelete(true)}
                className="text-xs px-2 py-1 rounded border"
                style={{ borderColor: 'var(--status-red)', color: '#f87171' }}
              >
                Eliminar
              </button>
            )}
          </div>
        </div>

        {/* Permissions row */}
        <div
          className="px-4 pb-3"
          style={{ borderTop: editing ? '1px solid var(--border-subtle)' : undefined }}
        >
          {editing ? (
            <div className="grid grid-cols-2 gap-2 pt-3">
              {PERM_LABELS.map(({ key, label }) => (
                <label key={key} className="flex items-center gap-2 text-sm cursor-pointer" style={{ color: 'var(--text-secondary)' }}>
                  <input
                    type="checkbox"
                    checked={perms[key as keyof RolePerms]}
                    onChange={(e) => setPerms({ ...perms, [key]: e.target.checked })}
                    className="accent-yellow-500"
                  />
                  {label}
                </label>
              ))}
            </div>
          ) : (
            <div className="flex flex-wrap gap-2 pt-1">
              {PERM_LABELS.map(({ key, label }) => (
                <StatusBadge key={key} ok={role[key] as boolean} label={label} />
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  );
}

function RolesSection({ roles, onRolesChange }: { roles: RoleInfo[]; onRolesChange: () => void }) {
  const [form, setForm] = useState({
    name: '', description: '',
    can_manage_users: false, can_manage_collections: false,
    can_upload_documents: false, can_delete_documents: false,
  });
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ text: string; type: 'ok' | 'err' } | null>(null);

  // Filter state
  const [roleSearch, setRoleSearch] = useState('');
  const [roleSearchD, setRoleSearchD] = useState('');
  const [roleTypeFilter, setRoleTypeFilter] = useState<'' | 'system' | 'custom'>('');

  const flash = (text: string, type: 'ok' | 'err' = 'ok') => {
    setMsg({ text, type });
    setTimeout(() => setMsg(null), 3000);
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await createRole(form);
      setForm({ name: '', description: '', can_manage_users: false, can_manage_collections: false, can_upload_documents: false, can_delete_documents: false });
      onRolesChange();
      flash('Rol creado');
    } catch (err) { flash(err instanceof Error ? err.message : 'Error', 'err'); }
    setBusy(false);
  };

  useEffect(() => {
    const t = setTimeout(() => setRoleSearchD(roleSearch), 250);
    return () => clearTimeout(t);
  }, [roleSearch]);

  const filteredRoles = useMemo(() => {
    let r = [...roles];
    if (roleSearchD.trim()) {
      const q = roleSearchD.toLowerCase();
      r = r.filter(ro => ro.name.toLowerCase().includes(q) || (ro.description ?? '').toLowerCase().includes(q));
    }
    if (roleTypeFilter === 'system') r = r.filter(ro => ro.is_system);
    if (roleTypeFilter === 'custom') r = r.filter(ro => !ro.is_system);
    return r;
  }, [roles, roleSearchD, roleTypeFilter]);

  const anyRoleFilter = roleSearch !== '' || roleTypeFilter !== '';

  return (
    <div className="space-y-6">
      {msg && <Toast msg={msg.text} type={msg.type} />}
      <Card>
        <SectionTitle>Crear Rol</SectionTitle>
        <form onSubmit={handleCreate} className="grid grid-cols-1 gap-3 max-w-md">
          <Input
            type="text" placeholder="Nombre del rol" required
            value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
          <Input
            type="text" placeholder="Descripción (opcional)"
            value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
          <div className="grid grid-cols-2 gap-2 pt-1">
            {PERM_LABELS.map(({ key, label }) => (
              <label key={key} className="flex items-center gap-2 text-sm cursor-pointer" style={{ color: 'var(--text-secondary)' }}>
                <input
                  type="checkbox"
                  checked={form[key] as boolean}
                  onChange={(e) => setForm({ ...form, [key]: e.target.checked })}
                  className="accent-yellow-500"
                />
                {label}
              </label>
            ))}
          </div>
          <BtnPrimary type="submit" disabled={busy}>
            <Plus size={14} /> {busy ? 'Creando...' : 'Crear Rol'}
          </BtnPrimary>
        </form>
      </Card>

      <Card>
        <div className="flex items-center justify-between mb-4">
          <SectionTitle>Roles</SectionTitle>
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>Los roles de sistema no se pueden eliminar ni editar sus permisos</span>
        </div>
        <div className="flex items-center gap-2 mb-3 flex-wrap">
          <div className="relative flex-1 min-w-[180px]">
            <Search size={12} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--text-muted)' }} />
            <Input type="text" placeholder="Buscar por nombre o descripción..." value={roleSearch}
              onChange={(e) => setRoleSearch(e.target.value)} style={{ paddingLeft: 30 }} />
          </div>
          <Select value={roleTypeFilter} onChange={(e) => setRoleTypeFilter(e.target.value as '' | 'system' | 'custom')} className="text-xs w-48">
            <option value="">Todos los roles</option>
            <option value="system">Solo sistema</option>
            <option value="custom">Solo personalizados</option>
          </Select>
          {anyRoleFilter && (
            <BtnGhost onClick={() => { setRoleSearch(''); setRoleTypeFilter(''); }}>
              <X size={12} /> Limpiar filtros
            </BtnGhost>
          )}
        </div>
        <p className="text-xs mb-2" style={{ color: 'var(--text-muted)' }}>{filteredRoles.length} de {roles.length} roles</p>
        <div className="space-y-3">
          {roles.length === 0 && (
            <p className="text-sm" style={{ color: 'var(--text-muted)' }}>No hay roles.</p>
          )}
          {roles.length > 0 && filteredRoles.length === 0 && (
            <p className="text-sm" style={{ color: 'var(--text-muted)' }}>No se encontraron roles con los filtros aplicados.</p>
          )}
          {filteredRoles.map((r) => (
            <RoleCard
              key={r.id}
              role={r}
              onSaved={onRolesChange}
              onDeleted={onRolesChange}
              flash={flash}
            />
          ))}
        </div>
      </Card>
    </div>
  );
}

// ── SECTION: Colecciones ───────────────────────────────────────────────────

function CollectionPermRow({
  entry,
  onSave,
}: {
  entry: RolePermEntry;
  onSave: (roleId: string, perms: { can_view: boolean; can_download: boolean; can_chat: boolean }) => void;
}) {
  const [on, setOn] = useState(entry.can_view || entry.can_download || entry.can_chat);

  const toggle = () => {
    const next = !on;
    setOn(next);
    onSave(entry.role_id, { can_view: next, can_download: next, can_chat: next });
  };

  return (
    <div className="flex items-center gap-3 py-2 px-3 rounded-lg" style={{ background: 'var(--bg-base)' }}>
      <span className="text-sm flex-1" style={{ color: 'var(--text-primary)' }}>{entry.role_name}</span>
      <div className="flex flex-col items-center gap-1">
        <span className="text-xs" style={{ color: 'var(--text-muted)' }}>Acceso</span>
        <button
          style={{
            width: 36, height: 20, borderRadius: 10,
            background: on ? 'var(--gold-muted)' : 'var(--bg-base)',
            border: `1px solid ${on ? 'var(--gold-bright)' : 'var(--border-default)'}`,
            position: 'relative', cursor: 'pointer', flexShrink: 0,
            transition: 'background 0.15s',
          }}
          onClick={toggle}
        >
          <div style={{
            position: 'absolute', top: 2,
            left: on ? 18 : 2, width: 14, height: 14,
            borderRadius: '50%',
            background: on ? 'var(--gold-bright)' : 'var(--text-muted)',
            transition: 'left 0.15s',
          }} />
        </button>
      </div>
    </div>
  );
}

function UserSearchInput({
  users,
  onSelect,
}: {
  users: UserOut[];
  onSelect: (user: UserOut) => void;
}) {
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState<UserOut | null>(null);
  const [showList, setShowList] = useState(false);

  const filtered = query.trim()
    ? users.filter((u) => u.username.toLowerCase().includes(query.toLowerCase()))
    : users;

  const pick = (u: UserOut) => {
    setSelected(u);
    setQuery('');
    setShowList(false);
    onSelect(u);
  };

  const clear = () => {
    setSelected(null);
    setQuery('');
  };

  return (
    <div className="relative flex-1">
      {selected ? (
        <div
          className="flex items-center gap-2 px-3 py-2 rounded-lg border text-sm"
          style={{ background: 'var(--bg-elevated)', borderColor: 'var(--border-default)', color: 'var(--text-primary)' }}
        >
          <span className="flex-1">{selected.username}</span>
          <button onClick={clear} style={{ color: 'var(--text-muted)' }}>
            <X size={12} />
          </button>
        </div>
      ) : (
        <input
          type="text"
          placeholder="Buscar usuario..."
          value={query}
          onChange={(e) => { setQuery(e.target.value); setShowList(true); }}
          onFocus={() => setShowList(true)}
          onBlur={() => setTimeout(() => setShowList(false), 150)}
          className="w-full px-3 py-2 rounded-lg border text-sm focus:outline-none focus:ring-1 focus:ring-yellow-600"
          style={{ background: 'var(--bg-elevated)', borderColor: 'var(--border-default)', color: 'var(--text-primary)' }}
        />
      )}
      {showList && !selected && filtered.length > 0 && (
        <div
          className="absolute z-10 w-full mt-1 rounded-lg border shadow-lg max-h-40 overflow-y-auto"
          style={{ background: 'var(--bg-elevated)', borderColor: 'var(--border-subtle)' }}
        >
          {filtered.map((u) => (
            <button
              key={u.id}
              onMouseDown={() => pick(u)}
              className="w-full text-left px-3 py-2 text-sm hover:bg-opacity-80 transition-colors"
              style={{ color: 'var(--text-primary)' }}
              onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--bg-surface)'; }}
              onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
            >
              {u.username}
              <span className="ml-2 text-xs" style={{ color: 'var(--text-muted)' }}>{u.role?.name ?? 'Sin rol'}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function CollectionCard({
  col, users, roles, onDeleted, flash,
}: { col: CollectionOut; users: UserOut[]; roles: RoleInfo[]; onDeleted: () => void; flash: (msg: string, type?: 'ok' | 'err') => void }) {
  const [open, setOpen] = useState(false);
  const [rolePerms, setRolePerms] = useState<RolePermEntry[]>([]);
  const [userPerms, setUserPerms] = useState<UserPermEntry[]>([]);
  const [addUser, setAddUser] = useState<UserOut | null>(null);
  const [searchResetKey, setSearchResetKey] = useState(0);
  const [loadingPerms, setLoadingPerms] = useState(false);
  const [deleteAction, setDeleteAction] = useState<'choose' | 'confirm-purge' | null>(null);
  const [deleteDocCount, setDeleteDocCount] = useState(0);
  const [deleteBusy, setDeleteBusy] = useState(false);

  const startDelete = async () => {
    setDeleteBusy(true);
    try {
      // Intento "auto": el backend hace hard delete si no hay docs, o devuelve 409 con conteo.
      const result = await deleteCollection(col.id, 'auto');
      if (result.deleted && !result.has_documents) {
        flash('Colección eliminada');
        onDeleted();
      }
    } catch (err) {
      if (err instanceof CollectionHasDocumentsError) {
        setDeleteDocCount(err.document_count);
        setDeleteAction('choose');
      } else {
        flash(err instanceof Error ? err.message : 'Error', 'err');
      }
    }
    setDeleteBusy(false);
  };

  const finishDelete = async (action: 'obsolete' | 'delete') => {
    setDeleteBusy(true);
    try {
      await deleteCollection(col.id, action);
      flash(
        action === 'obsolete'
          ? `Colección eliminada. ${deleteDocCount} documento(s) marcados como obsoletos.`
          : `Colección y ${deleteDocCount} documento(s) eliminados permanentemente.`,
      );
      setDeleteAction(null);
      onDeleted();
    } catch (err) {
      flash(err instanceof Error ? err.message : 'Error', 'err');
    }
    setDeleteBusy(false);
  };

  const loadPerms = useCallback(async () => {
    setLoadingPerms(true);
    try {
      const [rp, up] = await Promise.all([
        getCollectionRolePerms(col.id),
        getCollectionUserPerms(col.id),
      ]);
      setRolePerms(rp);
      setUserPerms(up);
    } catch {}
    setLoadingPerms(false);
  }, [col.id]);

  useEffect(() => { if (open) loadPerms(); }, [open, loadPerms]);

  const saveRolePerm = async (roleId: string, perms: { can_view: boolean; can_download: boolean; can_chat: boolean }) => {
    try { await updateCollectionRolePerm(col.id, roleId, perms); }
    catch {}
  };

  const addUserException = async () => {
    if (!addUser) return;
    try {
      await updateCollectionUserPerm(col.id, addUser.id, { can_view: true, can_download: true, can_chat: true });
      setAddUser(null);
      setSearchResetKey((k) => k + 1);
      await loadPerms();
    } catch {}
  };

  const removeUserException = async (userId: string) => {
    try { await deleteCollectionUserPerm(col.id, userId); await loadPerms(); }
    catch {}
  };

  const getUsernameById = (userId: string) =>
    users.find((u) => u.id === userId)?.username ?? userId.slice(0, 8) + '...';

  const usersWithoutException = users.filter(
    (u) => !userPerms.some((up) => up.user_id === u.id)
  );

  return (
    <div className="rounded-xl border overflow-hidden" style={{ borderColor: 'var(--border-subtle)' }}>
      {/* Modal de decisión cuando la colección tiene documentos */}
      <Dialog.Root open={!!deleteAction} onOpenChange={(o) => { if (!o && !deleteBusy) setDeleteAction(null); }}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm" />
          <Dialog.Content
            className="fixed z-50 top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-full max-w-md rounded-2xl p-6 shadow-2xl max-h-[90vh] overflow-y-auto"
            style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-default)' }}
          >
            <Dialog.Title
              className="text-base font-semibold mb-2"
              style={{ color: 'var(--gold-bright)', fontFamily: 'Playfair Display, serif' }}
            >
              {deleteAction === 'confirm-purge' ? 'Confirmar eliminación permanente' : 'Eliminar colección'}
            </Dialog.Title>
            <Dialog.Description className="text-sm mb-4" style={{ color: 'var(--text-secondary)' }}>
              La colección <strong>{col.name}</strong> tiene <strong>{deleteDocCount}</strong> documento(s).
              {deleteAction === 'confirm-purge' ? (
                <span> Esto borrará permanentemente los archivos, índices y vectores. <strong>No se puede deshacer.</strong></span>
              ) : (
                <span> Elige qué hacer con ellos:</span>
              )}
            </Dialog.Description>

            {deleteAction === 'choose' ? (
              <div className="space-y-2">
                <button
                  disabled={deleteBusy}
                  onClick={() => finishDelete('obsolete')}
                  className="w-full text-left px-4 py-3 rounded-lg border transition-colors disabled:opacity-50"
                  style={{ borderColor: 'var(--border-default)', color: 'var(--text-primary)', background: 'var(--bg-surface)' }}
                >
                  <div className="text-sm font-medium">Marcar documentos como obsoletos</div>
                  <div className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
                    Los documentos quedan sin colección y en estado obsoleto. Recuperables y descargables.
                  </div>
                </button>
                <button
                  disabled={deleteBusy}
                  onClick={() => setDeleteAction('confirm-purge')}
                  className="w-full text-left px-4 py-3 rounded-lg border transition-colors disabled:opacity-50"
                  style={{ borderColor: '#7f1d1d', color: '#f87171', background: 'var(--bg-surface)' }}
                >
                  <div className="text-sm font-medium">Eliminar todo permanentemente</div>
                  <div className="text-xs mt-0.5" style={{ color: '#fca5a5' }}>
                    Borra los archivos, fragmentos RAG y vectores. Irreversible.
                  </div>
                </button>
              </div>
            ) : (
              <div className="flex justify-end gap-2 mt-2">
                <button
                  disabled={deleteBusy}
                  onClick={() => setDeleteAction('choose')}
                  className="px-4 py-2 rounded-lg text-xs font-medium disabled:opacity-50"
                  style={{ color: 'var(--text-secondary)', border: '1px solid var(--border-default)', background: 'var(--bg-surface)' }}
                >
                  Atrás
                </button>
                <button
                  disabled={deleteBusy}
                  onClick={() => finishDelete('delete')}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold disabled:opacity-50"
                  style={{ background: '#7f1d1d', color: '#fee2e2' }}
                >
                  {deleteBusy && <Loader2 size={12} className="animate-spin" />}
                  Eliminar permanentemente
                </button>
              </div>
            )}

            <div className="flex justify-end mt-4">
              {deleteAction === 'choose' && (
                <Dialog.Close asChild>
                  <button
                    disabled={deleteBusy}
                    className="px-4 py-2 rounded-lg text-xs font-medium disabled:opacity-50"
                    style={{ color: 'var(--text-muted)' }}
                  >
                    Cancelar
                  </button>
                </Dialog.Close>
              )}
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>

      <div
        className="w-full flex items-center justify-between px-5 py-4 transition-colors"
        style={{ background: open ? 'var(--bg-elevated)' : 'var(--bg-surface)' }}
      >
        <button onClick={() => setOpen((o) => !o)} className="flex items-center gap-3 flex-1 text-left">
          <FolderOpen size={16} style={{ color: 'var(--gold-muted)' }} />
          <span className="font-medium text-sm" style={{ color: 'var(--text-primary)' }}>{col.name}</span>
          {col.description && (
            <span className="text-xs" style={{ color: 'var(--text-muted)' }}>— {col.description}</span>
          )}
          <StatusBadge ok={col.is_active} label={col.is_active ? 'activa' : 'inactiva'} />
        </button>
        <div className="flex items-center gap-2">
          <button
            onClick={startDelete}
            disabled={deleteBusy}
            className="text-xs px-2 py-1 rounded border transition-colors disabled:opacity-50"
            style={{ borderColor: 'var(--status-red)', color: '#f87171' }}
            title="Eliminar colección"
          >
            {deleteBusy ? <Loader2 size={11} className="animate-spin" /> : <Trash2 size={11} />}
          </button>
          <button onClick={() => setOpen((o) => !o)} className="p-1">
            {open ? <ChevronUp size={14} style={{ color: 'var(--text-muted)' }} /> : <ChevronDown size={14} style={{ color: 'var(--text-muted)' }} />}
          </button>
        </div>
      </div>

      {open && (
        <div className="px-5 py-4 space-y-5" style={{ background: 'var(--bg-elevated)', borderTop: '1px solid var(--border-subtle)' }}>
          {loadingPerms ? (
            <p className="text-sm" style={{ color: 'var(--text-muted)' }}>Cargando permisos...</p>
          ) : (
            <>
              {/* Role permissions */}
              <div>
                <p className="text-xs font-semibold mb-2 uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
                  Acceso por Rol
                </p>
                <div className="space-y-2">
                  {rolePerms
                    .filter((rp) => {
                      const r = roles.find((rr) => rr.id === rp.role_id);
                      return r && !ROLE_NAMES_HIDDEN_IN_COLLECTIONS.has(r.name);
                    })
                    .map((rp) => (
                      <CollectionPermRow key={rp.role_id} entry={rp} onSave={saveRolePerm} />
                    ))}
                  {rolePerms.filter((rp) => {
                    const r = roles.find((rr) => rr.id === rp.role_id);
                    return r && !ROLE_NAMES_HIDDEN_IN_COLLECTIONS.has(r.name);
                  }).length === 0 && (
                    <p className="text-xs" style={{ color: 'var(--text-muted)' }}>Sin permisos de rol configurados.</p>
                  )}
                </div>
              </div>

              {/* User exceptions */}
              <div>
                <p className="text-xs font-semibold mb-2 uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
                  Acceso Individual por Usuario
                </p>
                <div className="space-y-2 mb-3">
                  {userPerms.map((up) => (
                    <div key={up.user_id} className="flex items-center justify-between px-3 py-2 rounded-lg" style={{ background: 'var(--bg-base)' }}>
                      <span className="text-sm" style={{ color: 'var(--text-primary)' }}>
                        {getUsernameById(up.user_id)}
                      </span>
                      <div className="flex items-center gap-2">
                        <span
                          className="text-xs px-1.5 py-0.5 rounded"
                          style={{ background: 'rgba(45,122,79,0.2)', color: '#4ade80' }}
                        >
                          Acceso
                        </span>
                        <button
                          onClick={() => removeUserException(up.user_id)}
                          className="text-xs ml-1"
                          style={{ color: '#f87171' }}
                        >
                          ✕
                        </button>
                      </div>
                    </div>
                  ))}
                  {userPerms.length === 0 && (
                    <p className="text-xs" style={{ color: 'var(--text-muted)' }}>Sin excepciones individuales.</p>
                  )}
                </div>
                {usersWithoutException.length > 0 && (
                  <div className="flex items-center gap-2">
                    <UserSearchInput
                      key={searchResetKey}
                      users={usersWithoutException}
                      onSelect={(u) => setAddUser(u)}
                    />
                    <BtnGhost onClick={addUserException} disabled={!addUser}>
                      <Plus size={12} /> Agregar
                    </BtnGhost>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

type DocRolePermsForm = Record<string, { can_view: boolean; can_download: boolean; can_chat: boolean }>;

function ColeccionesSection({ roles }: { roles: RoleInfo[] }) {
  const [collections, setCollections] = useState<CollectionOut[]>([]);
  const [users, setUsers] = useState<UserOut[]>([]);
  const [msg, setMsg] = useState<{ text: string; type: 'ok' | 'err' } | null>(null);

  // Multi-step modal state
  const [modalOpen, setModalOpen] = useState(false);
  const [step, setStep] = useState(1);
  const [form, setForm] = useState({ name: '', description: '' });
  const [rolePermsForm, setRolePermsForm] = useState<DocRolePermsForm>({});
  const [busy, setBusy] = useState(false);

  // Filter state
  const [colSearch, setColSearch] = useState('');
  const [colSearchD, setColSearchD] = useState('');
  const [colStatusFilter, setColStatusFilter] = useState<'' | 'active' | 'inactive'>('');
  const [colSort, setColSort] = useState<'newest' | 'az'>('newest');

  const flash = (text: string, type: 'ok' | 'err' = 'ok') => {
    setMsg({ text, type });
    setTimeout(() => setMsg(null), 3000);
  };

  const load = useCallback(async () => {
    try {
      const [cols, usrs] = await Promise.all([getCollections(), getUsers()]);
      setCollections(cols);
      setUsers(usrs.items);
    } catch {}
  }, []);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    const t = setTimeout(() => setColSearchD(colSearch), 250);
    return () => clearTimeout(t);
  }, [colSearch]);

  const openModal = () => {
    const initial: DocRolePermsForm = {};
    selectableCollectionRoles(roles).forEach((r) => { initial[r.id] = { can_view: false, can_download: false, can_chat: false }; });
    setRolePermsForm(initial);
    setForm({ name: '', description: '' });
    setStep(1);
    setModalOpen(true);
  };

  const handleCreate = async () => {
    setBusy(true);
    try {
      const col = await createCollection(form);
      // Save all role permissions in parallel
      await Promise.all(
        Object.entries(rolePermsForm).map(([roleId, perms]) =>
          updateCollectionRolePerm(col.id, roleId, perms)
        )
      );
      setModalOpen(false);
      await load();
      flash('Colección creada');
    } catch (err) { flash(err instanceof Error ? err.message : 'Error', 'err'); }
    setBusy(false);
  };

  const toggleRolePerm = (roleId: string, key: 'can_view' | 'can_download' | 'can_chat', value: boolean) => {
    setRolePermsForm((prev) => ({
      ...prev,
      [roleId]: { ...prev[roleId], [key]: value },
    }));
  };

  const filteredCollections = useMemo(() => {
    let r = [...collections];
    if (colSearchD.trim()) {
      const q = colSearchD.toLowerCase();
      r = r.filter(c => c.name.toLowerCase().includes(q) || (c.description ?? '').toLowerCase().includes(q));
    }
    if (colStatusFilter === 'active')   r = r.filter(c => c.is_active);
    if (colStatusFilter === 'inactive') r = r.filter(c => !c.is_active);
    if (colSort === 'az')     r.sort((a, b) => a.name.localeCompare(b.name));
    if (colSort === 'newest') r.sort((a, b) => b.created_at.localeCompare(a.created_at));
    return r;
  }, [collections, colSearchD, colStatusFilter, colSort]);

  const anyColFilter = colSearch !== '' || colStatusFilter !== '' || colSort !== 'newest';

  return (
    <div className="space-y-6">
      {msg && <Toast msg={msg.text} type={msg.type} />}

      {/* Multi-step collection creation modal */}
      <Dialog.Root open={modalOpen} onOpenChange={(o) => { if (!busy) setModalOpen(o); }}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm" />
          <Dialog.Content
            className="fixed z-50 top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-full max-w-lg rounded-2xl p-6 shadow-2xl max-h-[90vh] overflow-y-auto"
            style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-default)' }}
          >
            {/* Step indicator */}
            <div className="flex items-center gap-2 mb-5">
              {[1, 2].map((s) => (
                <React.Fragment key={s}>
                  <div
                    className="w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold shrink-0"
                    style={{
                      background: step >= s ? 'var(--gold-bright)' : 'var(--bg-surface)',
                      color: step >= s ? '#0A1A10' : 'var(--text-muted)',
                      border: step >= s ? 'none' : '1px solid var(--border-default)',
                    }}
                  >
                    {s}
                  </div>
                  {s < 2 && (
                    <div className="w-8 h-px shrink-0" style={{ background: step > s ? 'var(--gold-bright)' : 'var(--border-default)' }} />
                  )}
                </React.Fragment>
              ))}
              <span className="ml-2 text-xs" style={{ color: 'var(--text-secondary)' }}>
                {step === 1 ? 'Datos básicos' : 'Permisos por rol'}
              </span>
            </div>

            <div className="flex items-center justify-between mb-4">
              <Dialog.Title
                className="text-base font-semibold"
                style={{ color: 'var(--gold-bright)', fontFamily: 'Playfair Display, serif' }}
              >
                Nueva Colección
              </Dialog.Title>
              {!busy && (
                <Dialog.Close asChild>
                  <button className="p-1 rounded-md" style={{ color: 'var(--text-muted)' }}>
                    <X size={14} />
                  </button>
                </Dialog.Close>
              )}
            </div>

            <Dialog.Description className="sr-only">
              Formulario de creación de colección en {step === 1 ? 'paso 1: datos básicos' : 'paso 2: permisos por rol'}
            </Dialog.Description>

            {step === 1 ? (
              <div className="space-y-3">
                <Input
                  type="text"
                  placeholder="Nombre de la colección"
                  required
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  autoFocus
                />
                <Input
                  type="text"
                  placeholder="Descripción (opcional)"
                  value={form.description}
                  onChange={(e) => setForm({ ...form, description: e.target.value })}
                />
              </div>
            ) : (
              <div>
                <p className="text-xs mb-3" style={{ color: 'var(--text-muted)' }}>
                  Define qué roles tendrán acceso a esta colección. Puedes ajustarlo después.
                </p>
                <div className="rounded-lg overflow-hidden" style={{ border: '1px solid var(--border-subtle)' }}>
                  {/* Table header */}
                  <div
                    className="grid grid-cols-[1fr_80px] gap-x-2 px-3 py-2 text-xs font-semibold uppercase tracking-wider"
                    style={{ background: 'var(--bg-surface)', color: 'var(--text-muted)', borderBottom: '1px solid var(--border-subtle)' }}
                  >
                    <span>Rol</span>
                    <span className="text-center">Acceso</span>
                  </div>
                  {/* Table rows */}
                  <div className="divide-y max-h-60 overflow-y-auto">
                    {selectableCollectionRoles(roles).map((r) => {
                      const p = rolePermsForm[r.id] ?? { can_view: false, can_download: false, can_chat: false };
                      const hasAccess = p.can_view || p.can_download || p.can_chat;
                      return (
                        <div
                          key={r.id}
                          className="grid grid-cols-[1fr_80px] gap-x-2 px-3 py-2.5 items-center"
                          style={{ background: 'var(--bg-elevated)' }}
                        >
                          <div>
                            <span className="text-sm" style={{ color: 'var(--text-primary)' }}>{r.name}</span>
                            {r.is_system && (
                              <span className="ml-2 text-xs px-1.5 py-0.5 rounded" style={{ background: 'rgba(234,179,8,0.12)', color: '#fbbf24' }}>
                                sistema
                              </span>
                            )}
                          </div>
                          <div className="flex justify-center">
                            <input
                              type="checkbox"
                              checked={hasAccess}
                              onChange={(e) => {
                                const v = e.target.checked;
                                toggleRolePerm(r.id, 'can_view', v);
                                toggleRolePerm(r.id, 'can_download', v);
                                toggleRolePerm(r.id, 'can_chat', v);
                              }}
                              className="accent-yellow-500 w-4 h-4 cursor-pointer"
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            )}

            <div className="flex justify-between mt-6">
              {step === 1 ? (
                <Dialog.Close asChild>
                  <button
                    className="px-4 py-2 rounded-lg text-xs font-medium"
                    style={{ color: 'var(--text-secondary)', border: '1px solid var(--border-default)', background: 'var(--bg-surface)' }}
                  >
                    Cancelar
                  </button>
                </Dialog.Close>
              ) : (
                <button
                  onClick={() => setStep(1)}
                  disabled={busy}
                  className="px-4 py-2 rounded-lg text-xs font-medium disabled:opacity-50"
                  style={{ color: 'var(--text-secondary)', border: '1px solid var(--border-default)', background: 'var(--bg-surface)' }}
                >
                  Atrás
                </button>
              )}
              {step === 1 ? (
                <button
                  onClick={() => { if (form.name.trim()) setStep(2); }}
                  disabled={!form.name.trim()}
                  className="px-4 py-2 rounded-lg text-xs font-semibold disabled:opacity-50"
                  style={{ background: 'var(--gold-bright)', color: '#0A1A10' }}
                >
                  Siguiente →
                </button>
              ) : (
                <button
                  onClick={handleCreate}
                  disabled={busy}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold disabled:opacity-50"
                  style={{ background: 'var(--gold-bright)', color: '#0A1A10' }}
                >
                  {busy && <Loader2 size={13} className="animate-spin" />}
                  {busy ? 'Creando...' : 'Crear Colección'}
                </button>
              )}
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>

      <Card>
        <div className="flex items-center justify-between mb-2">
          <SectionTitle>Colecciones</SectionTitle>
          <div className="flex items-center gap-2">
            <BtnGhost onClick={load}><RefreshCw size={12} /> Actualizar</BtnGhost>
            <BtnPrimary onClick={openModal}>
              <Plus size={14} /> Nueva Colección
            </BtnPrimary>
          </div>
        </div>
        <div className="flex items-center gap-2 mb-3 flex-wrap">
          <div className="relative flex-1 min-w-[180px]">
            <Search size={12} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--text-muted)' }} />
            <Input type="text" placeholder="Buscar por nombre o descripción..." value={colSearch}
              onChange={(e) => setColSearch(e.target.value)} style={{ paddingLeft: 30 }} />
          </div>
          <Select value={colStatusFilter} onChange={(e) => setColStatusFilter(e.target.value as '' | 'active' | 'inactive')} className="text-xs w-36">
            <option value="">Todas</option>
            <option value="active">Activas</option>
            <option value="inactive">Inactivas</option>
          </Select>
          <Select value={colSort} onChange={(e) => setColSort(e.target.value as 'newest' | 'az')} className="text-xs w-44">
            <option value="newest">Más recientes</option>
            <option value="az">Nombre A-Z</option>
          </Select>
          {anyColFilter && (
            <BtnGhost onClick={() => { setColSearch(''); setColStatusFilter(''); setColSort('newest'); }}>
              <X size={12} /> Limpiar filtros
            </BtnGhost>
          )}
        </div>
        <p className="text-xs mb-2" style={{ color: 'var(--text-muted)' }}>{filteredCollections.length} de {collections.length} colecciones</p>
        <div className="space-y-3">
          {collections.length === 0 && (
            <p className="text-sm" style={{ color: 'var(--text-muted)' }}>No hay colecciones. Crea la primera con el botón de arriba.</p>
          )}
          {collections.length > 0 && filteredCollections.length === 0 && (
            <p className="text-sm" style={{ color: 'var(--text-muted)' }}>No se encontraron colecciones con los filtros aplicados.</p>
          )}
          {filteredCollections.map((col) => (
            <CollectionCard key={col.id} col={col} users={users} roles={roles} onDeleted={load} flash={flash} />
          ))}
        </div>
      </Card>
    </div>
  );
}

// ── SECTION: Documentos ────────────────────────────────────────────────────

function DocUserPermsModal({
  doc,
  users,
  perms,
  loading,
  onAdd,
  onRemove,
  onClose,
}: {
  doc: PgDocumentOut;
  users: UserOut[];
  perms: DocUserPermEntry[];
  loading: boolean;
  onAdd: (userId: string) => Promise<void>;
  onRemove: (userId: string) => Promise<void>;
  onClose: () => void;
}) {
  const [addUser, setAddUser] = useState<UserOut | null>(null);
  const [searchResetKey, setSearchResetKey] = useState(0);
  const [busy, setBusy] = useState(false);

  const usersWithoutPerm = users.filter((u) => !perms.some((p) => p.user_id === u.id));

  const handleAdd = async () => {
    if (!addUser) return;
    setBusy(true);
    await onAdd(addUser.id);
    setAddUser(null);
    setSearchResetKey((k) => k + 1);
    setBusy(false);
  };

  return (
    <Dialog.Root open onOpenChange={(o) => { if (!o) onClose(); }}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm" />
        <Dialog.Content
          className="fixed z-50 top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-full max-w-md rounded-2xl p-6 shadow-2xl max-h-[90vh] overflow-y-auto"
          style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-default)' }}
        >
          <div className="flex items-center justify-between mb-4">
            <div>
              <Dialog.Title
                className="text-base font-semibold"
                style={{ color: 'var(--gold-bright)', fontFamily: 'Playfair Display, serif' }}
              >
                Acceso por Usuario
              </Dialog.Title>
              <p className="text-xs mt-0.5 truncate max-w-xs" style={{ color: 'var(--text-muted)' }}>
                {doc.original_filename}
              </p>
            </div>
            <Dialog.Close asChild>
              <button className="p-1 rounded-md" style={{ color: 'var(--text-muted)' }}>
                <X size={14} />
              </button>
            </Dialog.Close>
          </div>

          <Dialog.Description className="sr-only">
            Gestión de acceso individual por usuario para el documento {doc.original_filename}
          </Dialog.Description>

          {loading ? (
            <p className="text-sm py-4 text-center" style={{ color: 'var(--text-muted)' }}>Cargando...</p>
          ) : (
            <div className="space-y-3 max-h-60 overflow-y-auto mb-4">
              {perms.length === 0 && (
                <p className="text-xs py-2" style={{ color: 'var(--text-muted)' }}>Sin acceso individual asignado.</p>
              )}
              {perms.map((p) => (
                <div
                  key={p.user_id}
                  className="flex items-center justify-between px-3 py-2 rounded-lg"
                  style={{ background: 'var(--bg-base)' }}
                >
                  <span className="text-sm" style={{ color: 'var(--text-primary)' }}>{p.username}</span>
                  <div className="flex items-center gap-2">
                    <span className="text-xs px-1.5 py-0.5 rounded" style={{ background: 'rgba(45,122,79,0.2)', color: '#4ade80' }}>
                      Acceso
                    </span>
                    <button
                      onClick={() => onRemove(p.user_id)}
                      className="text-xs ml-1"
                      style={{ color: '#f87171' }}
                    >
                      ✕
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {usersWithoutPerm.length > 0 && (
            <div className="flex items-center gap-2 pt-2" style={{ borderTop: '1px solid var(--border-subtle)' }}>
              <UserSearchInput key={searchResetKey} users={usersWithoutPerm} onSelect={(u) => setAddUser(u)} />
              <BtnGhost onClick={handleAdd} disabled={!addUser || busy}>
                {busy ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />} Agregar
              </BtnGhost>
            </div>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function BulkUploadModal({
  files, collections, onClose, onDone, flash,
}: {
  files: File[];
  collections: CollectionOut[];
  onClose: () => void;
  onDone: () => void;
  flash: (msg: string, type?: 'ok' | 'err') => void;
}) {
  const [colId, setColId] = useState(''); // '' = sin asignar
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(0); // índice 1-based del archivo en curso
  const [currentName, setCurrentName] = useState('');

  // Sube los archivos uno por uno (igual que la ingesta de a uno: cada POST
  // dispara su pipeline en background y la cola de inferencia los serializa).
  // Continúa ante fallos y resume al final.
  const upload = async () => {
    setBusy(true);
    const failed: string[] = [];
    let ok = 0;
    for (let i = 0; i < files.length; i++) {
      setProgress(i + 1);
      setCurrentName(files[i].name);
      try {
        await uploadPgDocument(files[i], colId || null);
        ok += 1;
      } catch {
        failed.push(files[i].name);
      }
    }
    onDone();
    if (failed.length === 0) {
      const s = ok === 1 ? '' : 's';
      flash(`${ok} documento${s} subido${s} — procesando en segundo plano`);
    } else {
      const s = ok === 1 ? '' : 's';
      flash(`${ok} subido${s}, ${failed.length} con error: ${failed.join(', ')}`, 'err');
    }
    setBusy(false);
    onClose();
  };

  return (
    <Dialog.Root open onOpenChange={(o) => { if (!o && !busy) onClose(); }}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm" />
        <Dialog.Content
          className="fixed z-50 top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-full max-w-md rounded-2xl p-6 shadow-2xl max-h-[90vh] overflow-y-auto"
          style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-default)' }}
        >
          <Dialog.Title
            className="text-base font-semibold mb-2"
            style={{ color: 'var(--gold-bright)', fontFamily: 'Playfair Display, serif' }}
          >
            Confirmar subida ({files.length})
          </Dialog.Title>
          <Dialog.Description className="text-xs mb-3" style={{ color: 'var(--text-muted)' }}>
            Elige a qué colección subir {files.length === 1 ? 'el archivo' : 'los archivos'}.
          </Dialog.Description>

          <ul
            className="mb-3 space-y-1 max-h-48 overflow-y-auto rounded-lg border p-2"
            style={{ borderColor: 'var(--border-default)', background: 'var(--bg-surface)' }}
          >
            {files.map((f, i) => (
              <li key={i} className="flex items-center gap-2 text-xs" style={{ color: 'var(--text-secondary)' }}>
                <FileText size={12} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
                <span className="truncate">{f.name}</span>
              </li>
            ))}
          </ul>

          <Select value={colId} onChange={(e) => setColId(e.target.value)} disabled={busy}>
            <option value="">Sin asignar — decidir luego</option>
            {collections.filter((c) => c.is_active).map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </Select>

          {busy && (
            <p className="text-xs mt-3 flex items-center gap-2" style={{ color: 'var(--text-muted)' }}>
              <Loader2 size={12} className="animate-spin" />
              <span className="truncate">Subiendo {progress} de {files.length}: {currentName}</span>
            </p>
          )}

          <div className="flex justify-end gap-2 mt-5">
            <button
              disabled={busy}
              onClick={onClose}
              className="px-4 py-2 rounded-lg text-xs font-medium disabled:opacity-50"
              style={{ color: 'var(--text-secondary)', border: '1px solid var(--border-default)', background: 'var(--bg-surface)' }}
            >Cancelar</button>
            <button
              disabled={busy}
              onClick={upload}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold disabled:opacity-50"
              style={{ background: 'var(--gold-bright)', color: '#0A1A10' }}
            >
              {busy ? <Loader2 size={12} className="animate-spin" /> : <Upload size={12} />}
              Subir {files.length === 1 ? 'documento' : `${files.length} documentos`}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function MoveDocModal({
  doc, collections, onClose, onSaved, flash,
}: {
  doc: PgDocumentOut;
  collections: CollectionOut[];
  onClose: () => void;
  onSaved: () => void;
  flash: (msg: string, type?: 'ok' | 'err') => void;
}) {
  const [target, setTarget] = useState<string>(doc.collection_id ?? '__none__');
  const [busy, setBusy] = useState(false);

  const save = async () => {
    setBusy(true);
    try {
      await updatePgDocument(doc.doc_id, {
        collection_id: target === '__none__' ? null : target,
      });
      flash('Documento movido');
      onSaved();
      onClose();
    } catch (err) {
      flash(err instanceof Error ? err.message : 'Error', 'err');
    }
    setBusy(false);
  };

  return (
    <Dialog.Root open onOpenChange={(o) => { if (!o && !busy) onClose(); }}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm" />
        <Dialog.Content
          className="fixed z-50 top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-full max-w-md rounded-2xl p-6 shadow-2xl max-h-[90vh] overflow-y-auto"
          style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-default)' }}
        >
          <Dialog.Title
            className="text-base font-semibold mb-2"
            style={{ color: 'var(--gold-bright)', fontFamily: 'Playfair Display, serif' }}
          >
            Mover a colección
          </Dialog.Title>
          <Dialog.Description className="text-xs mb-3 truncate" style={{ color: 'var(--text-muted)' }}>
            {doc.original_filename}
          </Dialog.Description>
          <Select value={target} onChange={(e) => setTarget(e.target.value)}>
            <option value="__none__">— Sin colección —</option>
            {collections.filter((c) => c.is_active).map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </Select>
          <div className="flex justify-end gap-2 mt-5">
            <button
              disabled={busy}
              onClick={onClose}
              className="px-4 py-2 rounded-lg text-xs font-medium disabled:opacity-50"
              style={{ color: 'var(--text-secondary)', border: '1px solid var(--border-default)', background: 'var(--bg-surface)' }}
            >Cancelar</button>
            <button
              disabled={busy}
              onClick={save}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold disabled:opacity-50"
              style={{ background: 'var(--gold-bright)', color: '#0A1A10' }}
            >
              {busy && <Loader2 size={12} className="animate-spin" />}
              Mover
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function PermanentDeleteModal({
  doc, onClose, onConfirmed, flash,
}: {
  doc: PgDocumentOut;
  onClose: () => void;
  onConfirmed: () => void;
  flash: (msg: string, type?: 'ok' | 'err') => void;
}) {
  const [typed, setTyped] = useState('');
  const [busy, setBusy] = useState(false);
  const expected = doc.original_filename;
  const matches = typed.trim() === expected;

  const doPurge = async () => {
    if (!matches) return;
    setBusy(true);
    try {
      await permanentDeletePgDocument(doc.doc_id);
      flash('Documento eliminado permanentemente');
      onConfirmed();
      onClose();
    } catch (err) {
      flash(err instanceof Error ? err.message : 'Error', 'err');
    }
    setBusy(false);
  };

  return (
    <Dialog.Root open onOpenChange={(o) => { if (!o && !busy) onClose(); }}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm" />
        <Dialog.Content
          className="fixed z-50 top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-full max-w-md rounded-2xl p-6 shadow-2xl max-h-[90vh] overflow-y-auto"
          style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-default)' }}
        >
          <div className="flex items-center gap-2 mb-2">
            <AlertTriangle size={18} style={{ color: '#f87171' }} />
            <Dialog.Title
              className="text-base font-semibold"
              style={{ color: '#f87171', fontFamily: 'Playfair Display, serif' }}
            >
              Eliminar permanentemente
            </Dialog.Title>
          </div>
          <Dialog.Description className="text-sm mb-3" style={{ color: 'var(--text-secondary)' }}>
            Esta acción borra el archivo del disco, los fragmentos RAG y los vectores. <strong>No se puede deshacer.</strong>
          </Dialog.Description>
          <p className="text-xs mb-2" style={{ color: 'var(--text-muted)' }}>
            Escriba el nombre del archivo para confirmar:
          </p>
          <p className="text-xs mb-2 font-mono px-2 py-1 rounded" style={{ background: 'var(--bg-base)', color: 'var(--text-primary)' }}>
            {expected}
          </p>
          <Input value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="Nombre del archivo..." />
          <div className="flex justify-end gap-2 mt-5">
            <button
              disabled={busy}
              onClick={onClose}
              className="px-4 py-2 rounded-lg text-xs font-medium disabled:opacity-50"
              style={{ color: 'var(--text-secondary)', border: '1px solid var(--border-default)', background: 'var(--bg-surface)' }}
            >Cancelar</button>
            <button
              disabled={busy || !matches}
              onClick={doPurge}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold disabled:opacity-50"
              style={{ background: '#7f1d1d', color: '#fee2e2' }}
            >
              {busy && <Loader2 size={12} className="animate-spin" />}
              Eliminar para siempre
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function DocumentosSection({ canUpload, canDelete }: { canUpload: boolean; canDelete: boolean }) {
  const [docs, setDocs] = useState<PgDocumentOut[]>([]);
  const [collections, setCollections] = useState<CollectionOut[]>([]);
  const [users, setUsers] = useState<UserOut[]>([]);

  // Filtros
  const [search, setSearch] = useState('');
  const [filterCol, setFilterCol] = useState<string>(''); // '' = todas, '__none__' = sin colección, uuid = colección
  const [filterStatus, setFilterStatus] = useState<'' | 'ACTIVE' | 'OBSOLETE'>('');
  const [sort, setSort] = useState<PgDocumentsFilters['sort']>('newest');

  const [uploadFiles, setUploadFiles] = useState<File[]>([]); // archivos elegidos → abre el modal de confirmación
  const [downloading, setDownloading] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ text: string; type: 'ok' | 'err' } | null>(null);
  const [confirmObsolete, setConfirmObsolete] = useState<PgDocumentOut | null>(null);
  const [moveDoc, setMoveDoc] = useState<PgDocumentOut | null>(null);
  const [purgeDoc, setPurgeDoc] = useState<PgDocumentOut | null>(null);
  const [reactivatingId, setReactivatingId] = useState<string | null>(null);
  const [docPermsDoc, setDocPermsDoc] = useState<PgDocumentOut | null>(null);
  const [docPerms, setDocPerms] = useState<DocUserPermEntry[]>([]);
  const [docPermsLoading, setDocPermsLoading] = useState(false);

  const flash = useCallback((text: string, type: 'ok' | 'err' = 'ok') => {
    setMsg({ text, type });
    setTimeout(() => setMsg(null), 3000);
  }, []);

  const load = useCallback(async () => {
    try {
      const filters: PgDocumentsFilters = {};
      if (search.trim()) filters.search = search.trim();
      if (filterCol === '__none__') filters.uncategorized = true;
      else if (filterCol) filters.collection_id = filterCol;
      if (filterStatus) filters.status = filterStatus;
      if (sort) filters.sort = sort;

      const [d, c, u] = await Promise.all([getPgDocuments(filters), getCollections(), getUsers()]);
      setDocs(d);
      setCollections(c);
      setUsers(u.items);
    } catch {}
  }, [search, filterCol, filterStatus, sort]);

  const loadDocPerms = useCallback(async (docId: string) => {
    setDocPermsLoading(true);
    try {
      const p = await getDocumentUserPerms(docId);
      setDocPerms(p);
    } catch {}
    setDocPermsLoading(false);
  }, []);

  // Debounce: recarga 250ms después del último cambio en filtros.
  useEffect(() => {
    const t = setTimeout(load, 250);
    return () => clearTimeout(t);
  }, [load]);

  // Auto-refresh while any doc is pending/processing
  useEffect(() => {
    const hasPending = docs.some((d) => d.rag_status === 'pending' || d.rag_status === 'indexing_images');
    if (!hasPending) return;
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [docs, load]);

  const handleDownload = async (doc: PgDocumentOut) => {
    setDownloading(doc.doc_id);
    try { await downloadDocument(doc.doc_id, doc.original_filename); }
    catch (err) { flash(err instanceof Error ? err.message : 'Error al descargar', 'err'); }
    setDownloading(null);
  };

  const doObsolete = async () => {
    if (!confirmObsolete) return;
    try {
      await deletePgDocument(confirmObsolete.doc_id);
      await load();
      flash('Documento marcado como obsoleto');
    } catch (err) { flash(err instanceof Error ? err.message : 'Error', 'err'); }
    setConfirmObsolete(null);
  };

  const handleReactivate = async (doc: PgDocumentOut) => {
    setReactivatingId(doc.doc_id);
    try {
      await reactivatePgDocument(doc.doc_id);
      await load();
      flash(doc.collection_id ? 'Documento reactivado' : 'Documento reactivado en "Sin colección" — asígnele una colección');
    } catch (err) { flash(err instanceof Error ? err.message : 'Error', 'err'); }
    setReactivatingId(null);
  };

  const openDocPerms = (doc: PgDocumentOut) => {
    setDocPermsDoc(doc);
    setDocPerms([]);
    loadDocPerms(doc.doc_id);
  };

  const handleAddDocUserPerm = async (userId: string) => {
    if (!docPermsDoc) return;
    try {
      await updateDocumentUserPerm(docPermsDoc.doc_id, userId, { can_view: true, can_download: true, can_chat: true });
      await loadDocPerms(docPermsDoc.doc_id);
    } catch (err) { flash(err instanceof Error ? err.message : 'Error', 'err'); }
  };

  const handleRemoveDocUserPerm = async (userId: string) => {
    if (!docPermsDoc) return;
    try {
      await deleteDocumentUserPerm(docPermsDoc.doc_id, userId);
      await loadDocPerms(docPermsDoc.doc_id);
    } catch (err) { flash(err instanceof Error ? err.message : 'Error', 'err'); }
  };

  const visible = docs;

  return (
    <div className="space-y-6">
      {msg && <Toast msg={msg.text} type={msg.type} />}
      {docPermsDoc && (
        <DocUserPermsModal
          doc={docPermsDoc}
          users={users}
          perms={docPerms}
          loading={docPermsLoading}
          onAdd={handleAddDocUserPerm}
          onRemove={handleRemoveDocUserPerm}
          onClose={() => setDocPermsDoc(null)}
        />
      )}
      {moveDoc && (
        <MoveDocModal
          doc={moveDoc}
          collections={collections}
          onClose={() => setMoveDoc(null)}
          onSaved={load}
          flash={flash}
        />
      )}
      {purgeDoc && (
        <PermanentDeleteModal
          doc={purgeDoc}
          onClose={() => setPurgeDoc(null)}
          onConfirmed={load}
          flash={flash}
        />
      )}
      <ConfirmModal
        open={!!confirmObsolete}
        onOpenChange={(o) => { if (!o) setConfirmObsolete(null); }}
        title="Marcar como obsoleto"
        description={`¿Marcar "${confirmObsolete?.title || confirmObsolete?.original_filename}" como obsoleto? El documento dejará de aparecer en búsquedas y consultas pero seguirá siendo descargable.`}
        confirmLabel="Marcar obsoleto"
        destructive
        onConfirm={doObsolete}
      />
      {uploadFiles.length > 0 && (
        <BulkUploadModal
          files={uploadFiles}
          collections={collections}
          onClose={() => setUploadFiles([])}
          onDone={load}
          flash={flash}
        />
      )}

      {canUpload && (
        <Card>
          <SectionTitle>Subir Documentos</SectionTitle>
          <div className="grid grid-cols-1 gap-3 max-w-md">
            <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
              Selecciona uno o varios archivos. Luego eliges a qué colección subirlos.
            </p>
            <div
              className="flex items-center gap-3 px-3 py-2 rounded-lg border cursor-pointer"
              style={{ borderColor: 'var(--border-default)', background: 'var(--bg-elevated)' }}
              onClick={() => document.getElementById('file-input')?.click()}
            >
              <Upload size={14} style={{ color: 'var(--text-muted)' }} />
              <span className="text-sm" style={{ color: 'var(--text-muted)' }}>
                Seleccionar archivos...
              </span>
              <input
                id="file-input" type="file" className="hidden" multiple
                onChange={(e) => {
                  const files = Array.from(e.target.files ?? []);
                  if (files.length) setUploadFiles(files);
                  e.target.value = ''; // permite volver a elegir los mismos archivos
                }}
                accept=".pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx,.png,.jpg,.jpeg,.webp"
              />
            </div>
          </div>
        </Card>
      )}

      <Card>
        <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
          <SectionTitle>Documentos</SectionTitle>
          <BtnGhost onClick={load}><RefreshCw size={12} /> Actualizar</BtnGhost>
        </div>

        {/* Toolbar de filtros */}
        <div className="flex items-center gap-2 mb-4 flex-wrap">
          <div className="relative flex-1 min-w-[200px]">
            <Search size={12} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--text-muted)' }} />
            <Input
              type="text"
              placeholder="Buscar por nombre..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{ paddingLeft: 30 }}
            />
          </div>
          <Select
            value={filterCol}
            onChange={(e) => setFilterCol(e.target.value)}
            className="text-xs w-48"
          >
            <option value="">Todas las colecciones</option>
            <option value="__none__">⚠ Sin colección</option>
            {collections.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </Select>
          <Select
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value as '' | 'ACTIVE' | 'OBSOLETE')}
            className="text-xs w-36"
          >
            <option value="">Todos los estados</option>
            <option value="ACTIVE">Activos</option>
            <option value="OBSOLETE">Obsoletos</option>
          </Select>
          <Select
            value={sort}
            onChange={(e) => setSort(e.target.value as PgDocumentsFilters['sort'])}
            className="text-xs w-48"
          >
            <option value="newest">Más recientes primero</option>
            <option value="oldest_obsolete">Obsoletos más antiguos</option>
            <option value="name">Nombre A-Z</option>
          </Select>
        </div>

        {visible.length === 0 ? (
          <p className="text-sm" style={{ color: 'var(--text-muted)' }}>No hay documentos.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                  {['Nombre', 'Colección', 'Estado RAG', 'Tamaño', 'Fecha', 'Acciones'].map((h) => (
                    <th key={h} className="text-left py-2 px-3 text-xs font-semibold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {visible.map((doc) => {
                  const rag = RAG_LABEL[doc.rag_status] ?? RAG_LABEL['sin_rag'];
                  const isObsolete = doc.pg_status === 'OBSOLETE';
                  const noCol = !doc.collection_id;
                  return (
                    <tr
                      key={doc.doc_id}
                      style={{
                        borderBottom: '1px solid var(--border-subtle)',
                        opacity: isObsolete ? 0.65 : 1,
                      }}
                    >
                      <td className="py-3 px-3 max-w-xs">
                        <div className="flex items-center gap-2">
                          <FileText size={14} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
                          <span className="truncate" style={{ color: 'var(--text-primary)' }} title={doc.original_filename}>
                            {doc.original_filename}
                          </span>
                          {isObsolete && (
                            <span className="text-xs px-1.5 py-0.5 rounded" style={{ background: 'rgba(100,100,100,0.2)', color: '#9ca3af' }}>
                              obsoleto
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="py-3 px-3 whitespace-nowrap">
                        {noCol ? (
                          <span
                            className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full border"
                            style={{ background: 'rgba(245, 158, 11, 0.15)', color: '#fbbf24', borderColor: 'rgba(245, 158, 11, 0.4)' }}
                            title="Este documento no tiene colección asignada"
                          >
                            <AlertTriangle size={10} /> Sin colección
                          </span>
                        ) : (
                          <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: 'var(--gold-subtle)', color: 'var(--gold-bright)' }}>
                            {doc.collection_name}
                          </span>
                        )}
                      </td>
                      <td className="py-3 px-3 whitespace-nowrap">
                        <span
                          className="flex items-center gap-1 text-xs"
                          style={{ color: rag.color }}
                        >
                          {rag.icon} {rag.label}
                          {doc.rag_status === 'ready' && doc.rag_chunk_count > 0 && (
                            <span style={{ color: 'var(--text-muted)' }}>({doc.rag_chunk_count} fragmentos)</span>
                          )}
                        </span>
                      </td>
                      <td className="py-3 px-3 whitespace-nowrap text-xs" style={{ color: 'var(--text-secondary)' }}>
                        {formatBytes(doc.file_size_bytes)}
                      </td>
                      <td className="py-3 px-3 whitespace-nowrap text-xs" style={{ color: 'var(--text-secondary)' }}>
                        {formatDate(doc.created_at)}
                      </td>
                      <td className="py-3 px-3">
                        <div className="flex items-center gap-2 flex-wrap">
                          <button
                            onClick={() => handleDownload(doc)}
                            disabled={downloading === doc.doc_id}
                            className="flex items-center gap-1 text-xs px-2 py-1 rounded border transition-colors disabled:opacity-50"
                            style={{ borderColor: 'var(--border-default)', color: 'var(--text-secondary)' }}
                            title="Descargar"
                          >
                            {downloading === doc.doc_id
                              ? <Loader2 size={11} className="animate-spin" />
                              : <Download size={11} />}
                            Descargar
                          </button>
                          {canUpload && (
                            <button
                              onClick={() => setMoveDoc(doc)}
                              className="flex items-center gap-1 text-xs px-2 py-1 rounded border transition-colors"
                              style={{ borderColor: 'var(--border-default)', color: 'var(--text-secondary)' }}
                              title="Mover a otra colección"
                            >
                              <ArrowRightLeft size={11} /> Mover
                            </button>
                          )}
                          <button
                            onClick={() => openDocPerms(doc)}
                            className="flex items-center gap-1 text-xs px-2 py-1 rounded border transition-colors"
                            style={{ borderColor: 'var(--border-default)', color: 'var(--text-secondary)' }}
                            title="Gestionar acceso de usuarios"
                          >
                            <UserPlus size={11} /> Usuarios
                          </button>
                          {!isObsolete && canDelete && (
                            <button
                              onClick={() => setConfirmObsolete(doc)}
                              className="flex items-center gap-1 text-xs px-2 py-1 rounded border transition-colors"
                              style={{ borderColor: 'var(--status-red)', color: '#f87171' }}
                              title="Marcar como obsoleto"
                            >
                              <Trash2 size={11} /> Obsoleto
                            </button>
                          )}
                          {isObsolete && canUpload && (
                            <button
                              onClick={() => handleReactivate(doc)}
                              disabled={reactivatingId === doc.doc_id}
                              className="flex items-center gap-1 text-xs px-2 py-1 rounded border transition-colors disabled:opacity-50"
                              style={{ borderColor: '#2D7A4F', color: '#4ade80' }}
                              title="Reactivar documento"
                            >
                              {reactivatingId === doc.doc_id
                                ? <Loader2 size={11} className="animate-spin" />
                                : <RotateCcw size={11} />}
                              Reactivar
                            </button>
                          )}
                          {isObsolete && canDelete && (
                            <button
                              onClick={() => setPurgeDoc(doc)}
                              className="flex items-center gap-1 text-xs px-2 py-1 rounded text-white transition-colors"
                              style={{ background: '#7f1d1d' }}
                              title="Eliminar permanentemente"
                            >
                              <AlertTriangle size={11} /> Eliminar para siempre
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}

// ── MAIN PAGE ──────────────────────────────────────────────────────────────

export default function AdminPage() {
  const router = useRouter();
  const {
    user,
    isLoading,
    canManageUsers,
    canManageCollections,
    canUploadDocuments,
    canDeleteDocuments,
  } = useAuth();

  const [activeSection, setActiveSection] = useState('');
  const [roles, setRoles] = useState<RoleInfo[]>([]);

  const canUploadDocs = canUploadDocuments || canManageCollections;

  const loadRoles = useCallback(async () => {
    try { setRoles(await getRoles()); } catch {}
  }, []);

  useEffect(() => {
    if (isLoading) return;
    if (!user) { router.push('/login'); return; }
    if (!canManageUsers && !canManageCollections && !canUploadDocs) {
      router.push('/login');
      return;
    }

    if (!activeSection) {
      if (canManageUsers) setActiveSection('usuarios');
      else if (canManageCollections) setActiveSection('colecciones');
      else setActiveSection('documentos');
    }

    loadRoles();
  }, [user, isLoading, router, loadRoles, canManageUsers, canManageCollections, canUploadDocs, activeSection]);

  const navItems = [
    canManageUsers && { id: 'usuarios', label: 'Usuarios', icon: Users },
    canManageUsers && { id: 'roles', label: 'Roles', icon: Shield },
    canManageCollections && { id: 'colecciones', label: 'Colecciones', icon: FolderOpen },
    canUploadDocs && { id: 'documentos', label: 'Documentos', icon: FileText },
  ].filter(Boolean) as { id: string; label: string; icon: React.ElementType }[];

  if (isLoading || !user) return null;

  return (
    <div className="flex-1 flex flex-col min-h-0" style={{ background: 'var(--bg-base)' }}>
      {/* ── Body ── */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* Sidebar */}
        <aside
          className="shrink-0 w-48 flex flex-col py-4 px-2 gap-1"
          style={{ background: 'var(--bg-surface)', borderRight: '1px solid var(--border-subtle)' }}
        >
          {navItems.map((item) => (
            <NavItem
              key={item.id}
              id={item.id}
              label={item.label}
              icon={item.icon}
              active={activeSection === item.id}
              onClick={() => setActiveSection(item.id)}
            />
          ))}
        </aside>

        {/* Content */}
        <main className="flex-1 overflow-y-auto p-6">
          {activeSection === 'usuarios' && canManageUsers && (
            <UsuariosSection roles={roles} />
          )}
          {activeSection === 'roles' && canManageUsers && (
            <RolesSection roles={roles} onRolesChange={loadRoles} />
          )}
          {activeSection === 'colecciones' && canManageCollections && (
            <ColeccionesSection roles={roles} />
          )}
          {activeSection === 'documentos' && canUploadDocs && (
            <DocumentosSection canUpload={canUploadDocs} canDelete={canDeleteDocuments || canManageCollections} />
          )}
        </main>
      </div>
    </div>
  );
}
