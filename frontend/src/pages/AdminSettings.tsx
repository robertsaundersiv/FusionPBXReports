
import { useEffect, useMemo, useState } from 'react';
import { authService } from '../services/auth';
import { adminService } from '../services/admin';
import type { UserAccount, UserRole } from '../types';

type UserDraft = {
  role: UserRole;
};

export default function AdminSettings() {
  const [currentUser, setCurrentUser] = useState<UserAccount | null>(null);
  const [users, setUsers] = useState<UserAccount[]>([]);
  const [drafts, setDrafts] = useState<Record<number, UserDraft>>({});
  const [loading, setLoading] = useState(true);
  const [savingUserId, setSavingUserId] = useState<number | null>(null);
  const [deletingUserId, setDeletingUserId] = useState<number | null>(null);
  const [creatingUser, setCreatingUser] = useState(false);
  const [showAddUserForm, setShowAddUserForm] = useState(false);
  const [pageMessage, setPageMessage] = useState<string | null>(null);
  const [pageError, setPageError] = useState<string | null>(null);
  const [passwordForm, setPasswordForm] = useState({ currentPassword: '', newPassword: '', confirmPassword: '' });
  const [passwordSaving, setPasswordSaving] = useState(false);
  const [newUserForm, setNewUserForm] = useState({ username: '', email: '', password: '', confirmPassword: '', role: 'operator' as UserRole });

  useEffect(() => {
    let mounted = true;

    async function loadData() {
      try {
        setLoading(true);
        const me = await authService.getMe();
        if (!mounted) {
          return;
        }

        setCurrentUser(me);

        if (me.role !== 'operator') {
          const fetchedUsers = await adminService.getUsers();

          if (!mounted) {
            return;
          }

          setUsers(fetchedUsers);
          setDrafts(
            Object.fromEntries(
              fetchedUsers.map((user) => [
                user.id,
                {
                  role: user.role,
                },
              ])
            )
          );
        }
      } catch (error: any) {
        if (mounted) {
          setPageError(error.response?.data?.detail || 'Failed to load settings.');
        }
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    }

    loadData();

    return () => {
      mounted = false;
    };
  }, []);

  const isSuperAdmin = currentUser?.role === 'super_admin';
  const isAdmin = currentUser?.role === 'admin';
  const canManageUsers = isSuperAdmin || isAdmin;

  const manageableUsers = useMemo(() => {
    if (!canManageUsers) {
      return [];
    }

    return users.filter((user) => {
      if (isSuperAdmin) {
        return true;
      }
      return user.role === 'operator';
    });
  }, [canManageUsers, isSuperAdmin, users]);

  const roleOptions: UserRole[] = isSuperAdmin
    ? ['operator', 'admin', 'super_admin']
    : ['operator', 'admin'];

  const newUserRoleOptions: UserRole[] = isSuperAdmin
    ? ['operator', 'admin', 'super_admin']
    : ['operator', 'admin'];

  const updateDraft = (userId: number, key: keyof UserDraft, value: UserDraft[keyof UserDraft]) => {
    setDrafts((current) => ({
      ...current,
      [userId]: {
        ...current[userId],
        [key]: value,
      },
    }));
  };

  const handlePasswordChange = async (event: React.FormEvent) => {
    event.preventDefault();
    setPageMessage(null);
    setPageError(null);

    if (passwordForm.newPassword !== passwordForm.confirmPassword) {
      setPageError('New password and confirmation do not match.');
      return;
    }

    try {
      setPasswordSaving(true);
      const response = await authService.changePassword(passwordForm.currentPassword, passwordForm.newPassword);
      setPageMessage(response.message);
      setPasswordForm({ currentPassword: '', newPassword: '', confirmPassword: '' });
    } catch (error: any) {
      setPageError(error.response?.data?.detail || 'Unable to update password.');
    } finally {
      setPasswordSaving(false);
    }
  };

  const handleUserSave = async (user: UserAccount) => {
    const draft = drafts[user.id];
    if (!draft) {
      return;
    }

    setPageMessage(null);
    setPageError(null);

    try {
      setSavingUserId(user.id);
      const updatedUser = await adminService.updateUser(user.id, draft);
      setUsers((current) => current.map((entry) => (entry.id === user.id ? updatedUser : entry)));
      setPageMessage(`Updated ${updatedUser.username}.`);
    } catch (error: any) {
      setPageError(error.response?.data?.detail || `Unable to update ${user.username}.`);
    } finally {
      setSavingUserId(null);
    }
  };

  const handleUserDelete = async (user: UserAccount) => {
    const confirmed = window.confirm(`Delete user ${user.username}? This cannot be undone.`);
    if (!confirmed) {
      return;
    }

    setPageMessage(null);
    setPageError(null);

    try {
      setDeletingUserId(user.id);
      const response = await adminService.deleteUser(user.id);
      setUsers((current) => current.filter((entry) => entry.id !== user.id));
      setDrafts((current) => {
        const next = { ...current };
        delete next[user.id];
        return next;
      });
      setPageMessage(response.message || `Deleted ${user.username}.`);
    } catch (error: any) {
      setPageError(error.response?.data?.detail || `Unable to delete ${user.username}.`);
    } finally {
      setDeletingUserId(null);
    }
  };

  const handleCreateUser = async (event: React.FormEvent) => {
    event.preventDefault();
    setPageMessage(null);
    setPageError(null);

    if (newUserForm.password !== newUserForm.confirmPassword) {
      setPageError('New user password and confirmation do not match.');
      return;
    }

    try {
      setCreatingUser(true);
      const createdUser = await adminService.createUser({
        username: newUserForm.username.trim(),
        email: newUserForm.email.trim(),
        password: newUserForm.password,
        role: newUserForm.role,
      });

      setUsers((current) => [...current, createdUser]);
      setDrafts((current) => ({
        ...current,
        [createdUser.id]: {
          role: createdUser.role,
        },
      }));

      setNewUserForm({ username: '', email: '', password: '', confirmPassword: '', role: 'operator' });
      setShowAddUserForm(false);
      setPageMessage(`Created user ${createdUser.username}.`);
    } catch (error: any) {
      setPageError(error.response?.data?.detail || 'Unable to create user.');
    } finally {
      setCreatingUser(false);
    }
  };

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-gray-900">Settings</h1>
        <p className="mt-2 text-sm text-gray-600">
          Manage your password and, when permitted, update user roles.
        </p>
      </div>

      {pageMessage ? <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">{pageMessage}</div> : null}
      {pageError ? <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{pageError}</div> : null}

      {loading ? <div className="rounded-xl bg-white p-6 shadow-sm">Loading settings...</div> : null}

      {!loading && currentUser ? (
        <>
          <section className="grid gap-6 lg:grid-cols-[1.2fr_1fr]">
            <div className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-gray-200">
              <h2 className="text-lg font-semibold text-gray-900">Your Account</h2>
              <div className="mt-4 grid gap-4 sm:grid-cols-2">
                <div>
                  <p className="text-xs uppercase tracking-wide text-gray-500">Username</p>
                  <p className="mt-1 text-sm font-medium text-gray-900">{currentUser.username}</p>
                </div>
                <div>
                  <p className="text-xs uppercase tracking-wide text-gray-500">Role</p>
                  <p className="mt-1 text-sm font-medium uppercase text-gray-900">{currentUser.role}</p>
                </div>
                <div>
                  <p className="text-xs uppercase tracking-wide text-gray-500">Email</p>
                  <p className="mt-1 text-sm font-medium text-gray-900">{currentUser.email}</p>
                </div>
              </div>
            </div>

            <form onSubmit={handlePasswordChange} className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-gray-200">
              <h2 className="text-lg font-semibold text-gray-900">Reset Password</h2>
              <div className="mt-4 space-y-4">
                <label className="block text-sm text-gray-700">
                  Current password
                  <input
                    type="password"
                    value={passwordForm.currentPassword}
                    onChange={(event) => setPasswordForm((current) => ({ ...current, currentPassword: event.target.value }))}
                    className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2"
                    required
                  />
                </label>
                <label className="block text-sm text-gray-700">
                  New password
                  <input
                    type="password"
                    value={passwordForm.newPassword}
                    onChange={(event) => setPasswordForm((current) => ({ ...current, newPassword: event.target.value }))}
                    className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2"
                    required
                  />
                </label>
                <label className="block text-sm text-gray-700">
                  Confirm new password
                  <input
                    type="password"
                    value={passwordForm.confirmPassword}
                    onChange={(event) => setPasswordForm((current) => ({ ...current, confirmPassword: event.target.value }))}
                    className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2"
                    required
                  />
                </label>
              </div>
              <button
                type="submit"
                disabled={passwordSaving}
                className="mt-5 rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800 disabled:cursor-not-allowed disabled:bg-gray-400"
              >
                {passwordSaving ? 'Saving...' : 'Update Password'}
              </button>
            </form>
          </section>

          {canManageUsers ? (
            <section className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-gray-200">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <h2 className="text-lg font-semibold text-gray-900">User Management</h2>
                  <p className="mt-1 text-sm text-gray-600">
                    {isSuperAdmin
                      ? 'Super admins can update roles for every account.'
                      : 'Admins can promote operators to admin.'}
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    onClick={() => setShowAddUserForm((current) => !current)}
                    className="rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800"
                  >
                    {showAddUserForm ? 'Cancel' : 'Add User'}
                  </button>
                  <div className="rounded-full bg-gray-100 px-3 py-1 text-xs font-medium uppercase tracking-wide text-gray-600">
                    {manageableUsers.length} manageable users
                  </div>
                </div>
              </div>

              {showAddUserForm ? (
                <form onSubmit={handleCreateUser} className="mt-5 grid gap-3 rounded-xl border border-gray-200 bg-gray-50 p-4 md:grid-cols-5">
                  <input
                    type="text"
                    value={newUserForm.username}
                    onChange={(event) => setNewUserForm((current) => ({ ...current, username: event.target.value }))}
                    placeholder="Username"
                    className="rounded-lg border border-gray-300 px-3 py-2"
                    required
                  />
                  <input
                    type="email"
                    value={newUserForm.email}
                    onChange={(event) => setNewUserForm((current) => ({ ...current, email: event.target.value }))}
                    placeholder="Email"
                    className="rounded-lg border border-gray-300 px-3 py-2"
                    required
                  />
                  <input
                    type="password"
                    value={newUserForm.password}
                    onChange={(event) => setNewUserForm((current) => ({ ...current, password: event.target.value }))}
                    placeholder="Password"
                    className="rounded-lg border border-gray-300 px-3 py-2"
                    required
                  />
                  <input
                    type="password"
                    value={newUserForm.confirmPassword}
                    onChange={(event) => setNewUserForm((current) => ({ ...current, confirmPassword: event.target.value }))}
                    placeholder="Confirm password"
                    className="rounded-lg border border-gray-300 px-3 py-2"
                    required
                  />
                  <div className="flex gap-2">
                    <select
                      value={newUserForm.role}
                      onChange={(event) => setNewUserForm((current) => ({ ...current, role: event.target.value as UserRole }))}
                      className="w-full rounded-lg border border-gray-300 px-3 py-2"
                    >
                      {newUserRoleOptions.map((role) => (
                        <option key={role} value={role}>
                          {role}
                        </option>
                      ))}
                    </select>
                    <button
                      type="submit"
                      disabled={creatingUser}
                      className="rounded-lg bg-emerald-600 px-4 py-2 text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-emerald-300"
                    >
                      {creatingUser ? 'Creating...' : 'Create'}
                    </button>
                  </div>
                </form>
              ) : null}

              <div className="mt-6 overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200 text-sm">
                  <thead>
                    <tr className="text-left text-xs uppercase tracking-wide text-gray-500">
                      <th className="pb-3 pr-4">User</th>
                      <th className="pb-3 pr-4">Current Role</th>
                      <th className="pb-3 pr-4">Set Role</th>
                      <th className="pb-3">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {manageableUsers.map((user) => {
                      const draft = drafts[user.id];
                      return (
                        <tr key={user.id} className="align-top">
                          <td className="py-4 pr-4">
                            <div className="font-medium text-gray-900">{user.username}</div>
                            <div className="text-xs text-gray-500">{user.email}</div>
                          </td>
                          <td className="py-4 pr-4 uppercase text-gray-700">{user.role}</td>
                          <td className="py-4 pr-4">
                            <select
                              value={draft?.role || user.role}
                              onChange={(event) => updateDraft(user.id, 'role', event.target.value as UserRole)}
                              className="w-full rounded-lg border border-gray-300 px-3 py-2"
                            >
                              {roleOptions.map((role) => (
                                <option key={role} value={role}>
                                  {role}
                                </option>
                              ))}
                            </select>
                          </td>
                          <td className="py-4">
                            <div className="flex gap-2">
                              <button
                                type="button"
                                onClick={() => handleUserSave(user)}
                                disabled={savingUserId === user.id || deletingUserId === user.id}
                                className="rounded-lg bg-blue-600 px-4 py-2 text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-blue-300"
                              >
                                {savingUserId === user.id ? 'Saving...' : 'Save'}
                              </button>
                              <button
                                type="button"
                                onClick={() => handleUserDelete(user)}
                                disabled={deletingUserId === user.id || savingUserId === user.id}
                                className="rounded-lg bg-red-600 px-4 py-2 text-white hover:bg-red-700 disabled:cursor-not-allowed disabled:bg-red-300"
                              >
                                {deletingUserId === user.id ? 'Deleting...' : 'Delete'}
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
