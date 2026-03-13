import apiClient from './api';
import type { UserAccount } from '../types';

export const authService = {
  async getMe(): Promise<UserAccount> {
    const response = await apiClient.get('/api/v1/auth/me');
    return response.data;
  },

  async changePassword(currentPassword: string, newPassword: string): Promise<{ message: string }> {
    const response = await apiClient.post('/api/v1/auth/change-password', {
      current_password: currentPassword,
      new_password: newPassword,
    });
    return response.data;
  },
};