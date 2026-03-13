import apiClient from './api';
import type { Branch, UserAccount, UserRole } from '../types';

export const adminService = {
  async createUser(payload: { username: string; email: string; password: string; role: UserRole }): Promise<UserAccount> {
    const response = await apiClient.post('/api/v1/auth/register', payload);
    return response.data;
  },

  async getUsers(): Promise<UserAccount[]> {
    const response = await apiClient.get('/api/v1/admin/users');
    return response.data;
  },

  async getBranches(): Promise<Branch[]> {
    const response = await apiClient.get('/api/v1/admin/branches');
    return response.data;
  },

  async updateUser(userId: number, updates: { role?: UserRole; branch_id?: number | null; enabled?: boolean }): Promise<UserAccount> {
    const response = await apiClient.put(`/api/v1/admin/users/${userId}`, updates);
    return response.data;
  },

  async deleteUser(userId: number): Promise<{ message: string }> {
    const response = await apiClient.delete(`/api/v1/admin/users/${userId}`);
    return response.data;
  },

  async createBranch(payload: { name: string; description?: string }): Promise<Branch> {
    const response = await apiClient.post('/api/v1/admin/branches', payload);
    return response.data;
  },
};