'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { 
  getRoles, createRole, getUsers, createUser, getIncidents, createIncident, uploadDocument 
} from '@/lib/api';
import { LogOut } from 'lucide-react';

export default function AdminPage() {
  const router = useRouter();
  const [activeTab, setActiveTab] = useState('usuarios');
  const [roles, setRoles] = useState<any[]>([]);
  const [users, setUsers] = useState<any[]>([]);
  const [incidents, setIncidents] = useState<any[]>([]);
  
  const [newRole, setNewRole] = useState('');
  const [newUser, setNewUser] = useState({ email: '', password: '', role_id: '' });
  const [newIncident, setNewIncident] = useState({ description: '', solution: '', resolved_by: '' });
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadRoleId, setUploadRoleId] = useState('');
  const [uploading, setUploading] = useState(false);

  const fetchRoles = async () => setRoles(await getRoles());
  const fetchUsers = async () => setUsers(await getUsers());
  const fetchIncidents = async () => setIncidents(await getIncidents());

  useEffect(() => {
    const role = localStorage.getItem('role');
    if (role !== 'admin') {
      router.push('/login');
    } else {
      fetchRoles();
      fetchUsers();
      fetchIncidents();
    }
  }, [router]);

  const handleCreateRole = async (e: React.FormEvent) => {
    e.preventDefault();
    await createRole(newRole);
    setNewRole('');
    fetchRoles();
  };

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    await createUser(newUser);
    setNewUser({ email: '', password: '', role_id: '' });
    fetchUsers();
  };

  const handleCreateIncident = async (e: React.FormEvent) => {
    e.preventDefault();
    await createIncident(newIncident);
    setNewIncident({ description: '', solution: '', resolved_by: '' });
    fetchIncidents();
  };

  const handleUploadDocument = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!uploadFile) return;
    setUploading(true);
    try {
      await uploadDocument(uploadFile, uploadRoleId || undefined);
      alert('Documento subido con éxito');
      setUploadFile(null);
      setUploadRoleId('');
    } catch (err) {
      alert('Error al subir documento');
    }
    setUploading(false);
  };

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('role');
    router.push('/login');
  };

  return (
    <div>
      <div className="flex justify-between mb-6">
        <div className="space-x-4">
          {['usuarios', 'roles', 'documentos', 'incidencias'].map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-2 rounded capitalize ${activeTab === tab ? 'bg-yellow-600 text-white' : 'bg-gray-800 text-gray-300'}`}
              style={{
                background: activeTab === tab ? 'var(--gold-bright)' : 'var(--bg-elevated)',
                color: activeTab === tab ? 'var(--bg-default)' : 'var(--text-secondary)'
              }}
            >
              {tab}
            </button>
          ))}
        </div>
        <button onClick={handleLogout} className="flex items-center gap-2 text-red-400 hover:text-red-300">
          <LogOut size={16} /> Salir
        </button>
      </div>

      <div className="bg-gray-800 p-6 rounded-lg" style={{ background: 'var(--bg-surface)', borderColor: 'var(--border-subtle)', borderWidth: 1 }}>
        {activeTab === 'usuarios' && (
          <div>
            <h2 className="text-xl font-bold mb-4" style={{ color: 'var(--gold-bright)' }}>Registrar Usuario</h2>
            <form onSubmit={handleCreateUser} className="space-y-4 mb-8 max-w-md">
              <input type="email" placeholder="Correo" required value={newUser.email} onChange={e => setNewUser({...newUser, email: e.target.value})} className="w-full p-2 rounded" style={{ background: 'var(--bg-elevated)' }} />
              <input type="password" placeholder="Contraseña" required value={newUser.password} onChange={e => setNewUser({...newUser, password: e.target.value})} className="w-full p-2 rounded" style={{ background: 'var(--bg-elevated)' }} />
              <select required value={newUser.role_id} onChange={e => setNewUser({...newUser, role_id: e.target.value})} className="w-full p-2 rounded" style={{ background: 'var(--bg-elevated)' }}>
                <option value="">Seleccionar Rol</option>
                {roles.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
              </select>
              <button type="submit" className="px-4 py-2 rounded bg-yellow-600 text-black font-semibold">Crear Usuario</button>
            </form>
            <h3 className="text-lg font-semibold mb-2">Usuarios Registrados</h3>
            <ul className="space-y-2">
              {users.map(u => (
                <li key={u.id} className="p-3 rounded bg-gray-700" style={{ background: 'var(--bg-elevated)' }}>
                  {u.email} - Rol: {u.role.name}
                </li>
              ))}
            </ul>
          </div>
        )}

        {activeTab === 'roles' && (
          <div>
            <h2 className="text-xl font-bold mb-4" style={{ color: 'var(--gold-bright)' }}>Añadir Rol</h2>
            <form onSubmit={handleCreateRole} className="space-y-4 mb-8 max-w-md">
              <input type="text" placeholder="Nombre del Rol (ej: dba, so)" required value={newRole} onChange={e => setNewRole(e.target.value)} className="w-full p-2 rounded" style={{ background: 'var(--bg-elevated)' }} />
              <button type="submit" className="px-4 py-2 rounded bg-yellow-600 text-black font-semibold">Crear Rol</button>
            </form>
            <h3 className="text-lg font-semibold mb-2">Roles Actuales</h3>
            <ul className="space-y-2">
              {roles.map(r => (
                <li key={r.id} className="p-3 rounded bg-gray-700" style={{ background: 'var(--bg-elevated)' }}>{r.name}</li>
              ))}
            </ul>
          </div>
        )}

        {activeTab === 'documentos' && (
          <div>
            <h2 className="text-xl font-bold mb-4" style={{ color: 'var(--gold-bright)' }}>Subir Documento por Rol</h2>
            <form onSubmit={handleUploadDocument} className="space-y-4 max-w-md">
              <input type="file" required onChange={e => setUploadFile(e.target.files?.[0] || null)} className="w-full" />
              <select value={uploadRoleId} onChange={e => setUploadRoleId(e.target.value)} className="w-full p-2 rounded" style={{ background: 'var(--bg-elevated)' }}>
                <option value="">Cualquier Rol / Público</option>
                {roles.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
              </select>
              <button type="submit" disabled={uploading} className="px-4 py-2 rounded bg-yellow-600 text-black font-semibold disabled:opacity-50">
                {uploading ? 'Subiendo...' : 'Subir Documento'}
              </button>
            </form>
          </div>
        )}

        {activeTab === 'incidencias' && (
          <div>
            <h2 className="text-xl font-bold mb-4" style={{ color: 'var(--gold-bright)' }}>Registrar Incidencia</h2>
            <form onSubmit={handleCreateIncident} className="space-y-4 mb-8 max-w-md">
              <textarea placeholder="Descripción del problema" required value={newIncident.description} onChange={e => setNewIncident({...newIncident, description: e.target.value})} className="w-full p-2 rounded min-h-[80px]" style={{ background: 'var(--bg-elevated)' }} />
              <textarea placeholder="Solución" required value={newIncident.solution} onChange={e => setNewIncident({...newIncident, solution: e.target.value})} className="w-full p-2 rounded min-h-[80px]" style={{ background: 'var(--bg-elevated)' }} />
              <input type="text" placeholder="Nombre de quien resolvió" required value={newIncident.resolved_by} onChange={e => setNewIncident({...newIncident, resolved_by: e.target.value})} className="w-full p-2 rounded" style={{ background: 'var(--bg-elevated)' }} />
              <button type="submit" className="px-4 py-2 rounded bg-yellow-600 text-black font-semibold">Registrar Incidencia</button>
            </form>
            <h3 className="text-lg font-semibold mb-2">Incidencias Registradas</h3>
            <div className="space-y-4">
              {incidents.map(inc => (
                <div key={inc.id} className="p-4 rounded bg-gray-700" style={{ background: 'var(--bg-elevated)' }}>
                  <p><strong>Descripción:</strong> {inc.description}</p>
                  <p><strong>Solución:</strong> {inc.solution}</p>
                  <p className="text-sm mt-2 text-gray-400">Resuelto por: {inc.resolved_by}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
