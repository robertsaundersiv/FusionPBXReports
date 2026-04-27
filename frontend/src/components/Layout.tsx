import React, { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Menu, X, LogOut } from 'lucide-react';
import type { UserAccount } from '../types';

interface LayoutProps {
  children: React.ReactNode;
  currentUser: UserAccount | null;
}

export default function Layout({ children, currentUser }: LayoutProps) {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const location = useLocation();

  const handleLogout = () => {
    localStorage.removeItem('auth_token');
    window.location.href = '/login';
  };

  const navigation = [
    { name: 'Executive Overview', href: '/executive-overview' },
    { name: 'Wallboard', href: '/wallboard' },
    { name: 'Queue Performance', href: '/queue-performance' },
    { name: 'Queue Performance Report', href: '/queue-performance-report' },
    { name: 'Agent Performance', href: '/agent-performance' },
    { name: 'Agent Performance Report', href: '/agent-performance-report' },
    { name: 'Outbound Calls', href: '/outbound-calls' },
    { name: 'Repeat Callers', href: '/repeat-callers' },
    { name: 'Day Comparer', href: '/day-comparer' },
    ...(currentUser?.role === 'super_admin'
      ? [{ name: 'Quality & Health', href: '/quality-health' }]
      : []),
    { name: 'Settings', href: '/admin/settings' },
  ];

  return (
    <div className="flex h-screen bg-gray-100">
      {/* Sidebar */}
      <div className={`${sidebarOpen ? 'w-64' : 'w-20'} bg-gray-900 text-white transition-all duration-300 flex flex-col`}>
        <div className="p-4 border-b border-gray-700 flex items-center justify-between">
          {sidebarOpen && <h1 className="text-xl font-bold">PhoneReports</h1>}
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="p-1 hover:bg-gray-800 rounded"
          >
            {sidebarOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>

        <nav className="flex-1 p-4 space-y-2">
          {navigation.map((item) => (
            <Link
              key={item.href}
              to={item.href}
              className={`flex items-center space-x-3 px-4 py-2 rounded-lg transition-colors ${
                location.pathname === item.href
                  ? 'bg-blue-600 text-white'
                  : 'text-gray-300 hover:bg-gray-800'
              }`}
              title={!sidebarOpen ? item.name : undefined}
            >
              <span className="w-5 h-5">{/* Icon placeholder */}</span>
              {sidebarOpen && <span>{item.name}</span>}
            </Link>
          ))}
        </nav>

        <div className="p-4 border-t border-gray-700">
          {sidebarOpen ? (
            <div>
              <div className="text-sm text-gray-400 mb-2">
                <p>Logged in as</p>
                <p className="font-semibold text-white">{currentUser?.username || 'Unknown User'}</p>
                <p className="text-xs uppercase tracking-wide">{currentUser?.role || 'guest'}</p>
              </div>
              <button
                onClick={handleLogout}
                className="w-full flex items-center space-x-2 px-3 py-2 text-sm bg-red-600 hover:bg-red-700 text-white rounded transition-colors"
              >
                <LogOut size={16} />
                <span>Logout</span>
              </button>
            </div>
          ) : (
            <button
              onClick={handleLogout}
              className="w-full p-2 text-red-400 hover:bg-gray-800 rounded transition-colors"
              title="Logout"
            >
              <LogOut size={20} />
            </button>
          )}
        </div>
      </div>

      {/* Main content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <div className="bg-white border-b border-gray-200 p-6 flex items-center justify-between">
          <h2 className="text-2xl font-bold text-gray-900">FusionPBX Analytics</h2>
          <div className="text-sm text-gray-600">
            {new Date().toLocaleDateString('en-US', {
              weekday: 'long',
              year: 'numeric',
              month: 'long',
              day: 'numeric',
            })}
          </div>
        </div>

        {/* Main content area */}
        <main className="flex-1 overflow-auto">
          {children}
        </main>
      </div>
    </div>
  );
}
