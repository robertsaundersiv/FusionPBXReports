import apiClient from './api';
import type { AgentGroupRule, Branch, UserAccount, UserRole } from '../types';

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

  async deleteBranch(branchId: number): Promise<{ message: string }> {
    const response = await apiClient.delete(`/api/v1/admin/branches/${branchId}`);
    return response.data;
  },

  async getAgentGroupRules(): Promise<AgentGroupRule[]> {
    const response = await apiClient.get('/api/v1/admin/agent-group-rules');
    return response.data;
  },

  async createAgentGroupRule(payload: { match_value: string; branch_id: number; enabled?: boolean; priority?: number }): Promise<AgentGroupRule> {
    const response = await apiClient.post('/api/v1/admin/agent-group-rules', payload);
    return response.data;
  },

  async deleteAgentGroupRule(ruleId: number): Promise<{ message: string }> {
    const response = await apiClient.delete(`/api/v1/admin/agent-group-rules/${ruleId}`);
    return response.data;
  },
};