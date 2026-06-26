'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import * as Dialog from '@radix-ui/react-dialog';
import { Eye, EyeOff } from 'lucide-react';
import { login, sendVerificationCode, verifyFirstLogin, MustChangePasswordError } from '@/lib/api';
import { useAuth } from '@/lib/auth-context';

export default function LoginPage() {
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [forgotOpen, setForgotOpen] = useState(false);
  
  // First login state
  const [step, setStep] = useState<'login' | 'verify'>('login');
  const [verificationCode, setVerificationCode] = useState('');
  const [newPassword, setNewPassword] = useState('');
  
  const router = useRouter();
  const { refetch } = useAuth();

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    if (step === 'login') {
      try {
        const data = await login(identifier, password);
        await finishLogin(data);
      } catch (err: unknown) {
        if (err instanceof MustChangePasswordError) {
          try {
            await sendVerificationCode(identifier, password);
            setStep('verify');
            setError('');
          } catch (sendErr: unknown) {
            setError(sendErr instanceof Error ? sendErr.message : 'Error al enviar el código');
          }
        } else {
          setError(err instanceof Error ? err.message : 'Error al iniciar sesión');
          setPassword('');
        }
      } finally {
        setLoading(false);
      }
    } else {
      // step === 'verify'
      try {
        const data = await verifyFirstLogin(identifier, password, verificationCode, newPassword);
        await finishLogin(data);
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : 'Error al verificar');
      } finally {
        setLoading(false);
      }
    }
  };

  const finishLogin = async (data: any) => {
    localStorage.setItem('access_token', data.access_token);
    localStorage.setItem('user', JSON.stringify(data.user));
    await refetch();

    const role = data.user.role;
    if (role && (role.can_manage_users || role.can_manage_collections || role.can_upload_documents)) {
      router.push('/admin');
    } else {
      router.push('/chat');
    }
  };

  return (
    <div
      className="min-h-screen flex items-center justify-center"
      style={{ background: 'var(--bg-default)' }}
    >
      <div
        className="max-w-md w-full p-8 rounded-xl shadow-lg border"
        style={{ background: 'var(--bg-surface)', borderColor: 'var(--border-subtle)' }}
      >
        <h2
          className="text-2xl font-bold text-center mb-6"
          style={{ color: 'var(--gold-bright)' }}
        >
          Iniciar Sesión
        </h2>

        {error && (
          <div className="mb-4 p-3 rounded bg-red-900/50 text-red-200 border border-red-800 text-sm">
            {error}
          </div>
        )}

        <form onSubmit={handleLogin} className="space-y-4">
          {step === 'login' && (
            <>
              <div>
                <label className="block text-sm font-medium mb-1 text-gray-300">Correo electrónico</label>
                <input
                  type="text"
                  value={identifier}
                  onChange={(e) => setIdentifier(e.target.value)}
                  required
                  autoComplete="email"
                  placeholder="correo@bmsc.com.bo"
                  className="w-full px-4 py-2 rounded border focus:outline-none focus:ring-1 focus:ring-yellow-500"
                  style={{
                    background: 'var(--bg-elevated)',
                    borderColor: 'var(--border-default)',
                    color: 'white',
                  }}
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1 text-gray-300">Contraseña</label>
                <div className="relative">
                  <input
                    type={showPassword ? 'text' : 'password'}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    autoComplete="current-password"
                    className="w-full px-4 py-2 rounded border focus:outline-none focus:ring-1 focus:ring-yellow-500"
                    style={{
                      background: 'var(--bg-elevated)',
                      borderColor: 'var(--border-default)',
                      color: 'white',
                      paddingRight: 40,
                    }}
                  />
                  <button
                    type="button"
                    tabIndex={-1}
                    onClick={() => setShowPassword((v) => !v)}
                    aria-label={showPassword ? 'Ocultar contraseña' : 'Mostrar contraseña'}
                    className="absolute right-3 top-1/2 -translate-y-1/2 transition-colors"
                    style={{ color: 'var(--text-secondary)' }}
                    onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--gold-bright)')}
                    onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--text-secondary)')}
                  >
                    {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                </div>
              </div>
            </>
          )}

          {step === 'verify' && (
            <>
              <div className="text-sm text-gray-300 mb-4 p-3 bg-blue-900/20 border border-blue-800/50 rounded-lg">
                Es tu primer inicio de sesión. Por seguridad, te hemos enviado un <strong>código de verificación</strong> a tu correo para cambiar tu contraseña.
              </div>
              <div>
                <label className="block text-sm font-medium mb-1 text-gray-300">Código de Verificación (6 dígitos)</label>
                <input
                  type="text"
                  value={verificationCode}
                  onChange={(e) => setVerificationCode(e.target.value)}
                  required
                  maxLength={6}
                  placeholder="Ej: 123456"
                  className="w-full px-4 py-2 rounded border focus:outline-none focus:ring-1 focus:ring-yellow-500 text-center tracking-widest text-lg"
                  style={{
                    background: 'var(--bg-elevated)',
                    borderColor: 'var(--border-default)',
                    color: 'var(--gold-bright)',
                  }}
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1 text-gray-300">Nueva Contraseña</label>
                <div className="relative">
                  <input
                    type={showPassword ? 'text' : 'password'}
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    required
                    autoComplete="new-password"
                    className="w-full px-4 py-2 rounded border focus:outline-none focus:ring-1 focus:ring-yellow-500"
                    style={{
                      background: 'var(--bg-elevated)',
                      borderColor: 'var(--border-default)',
                      color: 'white',
                      paddingRight: 40,
                    }}
                  />
                  <button
                    type="button"
                    tabIndex={-1}
                    onClick={() => setShowPassword((v) => !v)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 transition-colors"
                    style={{ color: 'var(--text-secondary)' }}
                  >
                    {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                </div>
              </div>
            </>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2 px-4 rounded font-medium transition-colors disabled:opacity-60"
            style={{ background: 'var(--gold-muted)', color: 'var(--bg-default)' }}
            onMouseEnter={(e) =>
              !loading && (e.currentTarget.style.background = 'var(--gold-bright)')
            }
            onMouseLeave={(e) =>
              (e.currentTarget.style.background = 'var(--gold-muted)')
            }
          >
            {loading ? 'Procesando...' : step === 'login' ? 'Ingresar' : 'Cambiar contraseña e ingresar'}
          </button>
          
          {step === 'login' && (
            <div className="text-center pt-2">
              <button
                type="button"
                onClick={() => setForgotOpen(true)}
                className="text-xs underline hover:no-underline"
                style={{ color: 'var(--text-secondary)' }}
              >
                ¿Olvidó su contraseña?
              </button>
            </div>
          )}
          
          {step === 'verify' && (
            <div className="text-center pt-2">
              <button
                type="button"
                onClick={() => setStep('login')}
                className="text-xs underline hover:no-underline"
                style={{ color: 'var(--text-secondary)' }}
              >
                Volver
              </button>
            </div>
          )}
        </form>
      </div>

      <Dialog.Root open={forgotOpen} onOpenChange={setForgotOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm" />
          <Dialog.Content
            className="fixed z-50 top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-full max-w-md rounded-2xl p-6 shadow-2xl"
            style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-default)' }}
          >
            <Dialog.Title
              className="text-base font-semibold mb-2"
              style={{ color: 'var(--gold-bright)', fontFamily: 'Playfair Display, serif' }}
            >
              Recuperar contraseña
            </Dialog.Title>
            <Dialog.Description className="text-sm leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
              Por seguridad, las contraseñas no se pueden recuperar desde aquí.
              Comuníquese con el <strong>encargado del sistema</strong> para que reestablezca su contraseña.
            </Dialog.Description>
            <div className="flex justify-end mt-5">
              <Dialog.Close asChild>
                <button
                  className="px-4 py-2 rounded-lg text-xs font-semibold"
                  style={{ background: 'var(--gold-bright)', color: '#0A1A10' }}
                >
                  Entendido
                </button>
              </Dialog.Close>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </div>
  );
}
