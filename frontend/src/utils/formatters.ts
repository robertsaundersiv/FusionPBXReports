import { startOfDay, endOfDay, subDays, format } from 'date-fns';

export const dateUtils = {
  getDateRangeByPreset(preset: string): { startDate: Date; endDate: Date } {
    const endDate = new Date();
    let startDate = new Date();

    switch (preset) {
      case 'today':
        startDate = startOfDay(new Date());
        break;
      case 'yesterday':
        startDate = startOfDay(subDays(new Date(), 1));
        endDate.setHours(0, 0, 0, 0);
        break;
      case 'last_7':
        startDate = startOfDay(subDays(new Date(), 6));
        break;
      case 'last_30':
        startDate = startOfDay(subDays(new Date(), 29));
        break;
    }

    return { startDate, endDate: endOfDay(endDate) };
  },

  formatDateForAPI(date: Date): string {
    return format(date, 'yyyy-MM-dd\'T\'HH:mm:ss\'Z\'');
  },

  formatDateForDisplay(date: Date, fmt: string = 'MMM dd, yyyy'): string {
    return format(date, fmt);
  },
};

export const numberUtils = {
  formatPercent(value: number, decimals: number = 1): string {
    return `${value.toFixed(decimals)}%`;
  },

  formatSeconds(seconds: number): string {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;

    if (hours > 0) {
      return `${hours}h ${minutes}m ${secs}s`;
    }
    if (minutes > 0) {
      return `${minutes}m ${secs}s`;
    }
    return `${secs}s`;
  },

  formatNumber(value: number): string {
    return new Intl.NumberFormat('en-US').format(value);
  },

  abbreviateNumber(value: number): string {
    if (value >= 1000000) {
      return (value / 1000000).toFixed(1) + 'M';
    }
    if (value >= 1000) {
      return (value / 1000).toFixed(1) + 'K';
    }
    return value.toString();
  },
};

export const maskPhoneNumber = (phone: string, role: 'admin' | 'manager' | 'user' = 'user'): string => {
  if (role === 'admin') {
    return phone;
  }

  if (phone.length <= 4) {
    return '****';
  }

  const lastFour = phone.slice(-4);
  const masked = '*'.repeat(phone.length - 4);
  return masked + lastFour;
};
