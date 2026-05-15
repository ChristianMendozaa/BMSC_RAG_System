'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { API_URL } from '@/lib/api';

export default function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const router = useRouter();

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    const formData = new URLSearchParams();
    formData.append('username', email);
    formData.append('password', password);

    try {
      const res = await fetch(`${API_URL}/api/auth/token`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: formData,
      });

      if (!res.ok) {
        throw new Error('Credenciales incorrectas');
      }

      const data = await res.json();
      localStorage.setItem('token', data.access_token);

      // Fetch user profile to check role
      const profileRes = await fetch(`${API_URL}/api/auth/me`, {
        headers: {
          'Authorization': `Bearer ${data.access_token}`
        }
      });
      const profile = await profileRes.json();
      localStorage.setItem('role', profile.role.name);

      if (profile.role.name === 'admin') {
        router.push('/admin');
      } else {
        router.push('/chat');
      }
    } catch (err: any) {
      setError(err.message || 'Error al iniciar sesión');
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-900" style={{ background: 'var(--bg-default)' }}>
      <div className="max-w-md w-full p-8 rounded-xl shadow-lg border" style={{ background: 'var(--bg-surface)', borderColor: 'var(--border-subtle)' }}>
        <h2 className="text-2xl font-bold text-center mb-6" style={{ color: 'var(--gold-bright)' }}>Iniciar Sesión</h2>
        {error && <div className="mb-4 p-3 rounded bg-red-900/50 text-red-200 border border-red-800 text-sm">{error}</div>}
        <form onSubmit={handleLogin} className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1 text-gray-300">Correo Electrónico</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="w-full px-4 py-2 rounded border focus:outline-none focus:ring-1 focus:ring-yellow-500"
              style={{ background: 'var(--bg-elevated)', borderColor: 'var(--border-default)', color: 'white' }}
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1 text-gray-300">Contraseña</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="w-full px-4 py-2 rounded border focus:outline-none focus:ring-1 focus:ring-yellow-500"
              style={{ background: 'var(--bg-elevated)', borderColor: 'var(--border-default)', color: 'white' }}
            />
          </div>
          <button
            type="submit"
            className="w-full py-2 px-4 rounded font-medium transition-colors"
            style={{ background: 'var(--gold-muted)', color: 'var(--bg-default)' }}
            onMouseEnter={(e) => e.currentTarget.style.background = 'var(--gold-bright)'}
            onMouseLeave={(e) => e.currentTarget.style.background = 'var(--gold-muted)'}
          >
            Ingresar
          </button>
        </form>
      </div>
    </div>
  );
}
