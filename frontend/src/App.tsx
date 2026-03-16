import React, { Suspense, useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import Login from './pages/Login';
import { authService } from './services/auth';
import type { UserAccount } from './types';
import './index.css';

// Pages with lazy loading
const ExecutiveOverview = React.lazy(() => import('./pages/ExecutiveOverview'));
const QueuePerformance = React.lazy(() => import('./pages/QueuePerformance'));
const QueuePerformanceReport = React.lazy(() => import('./pages/QueuePerformanceReportPage'));
const AgentPerformance = React.lazy(() => import('./pages/AgentPerformance'));
const AgentPerformanceReport = React.lazy(() => import('./pages/AgentPerformanceReportPage'));
const OutboundCalls = React.lazy(() => import('./pages/OutboundCalls'));
const QualityHealth = React.lazy(() => import('./pages/QualityHealth'));
const RepeatCallers = React.lazy(() => import('./pages/RepeatCallers'));
const AdminSettings = React.lazy(() => import('./pages/AdminSettings'));

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);
  const [authLoading, setAuthLoading] = useState<boolean>(true);
  const [currentUser, setCurrentUser] = useState<UserAccount | null>(null);

  useEffect(() => {
    const token = localStorage.getItem('auth_token');
    if (!token) {
      setIsAuthenticated(false);
      setCurrentUser(null);
      setAuthLoading(false);
      return;
    }

    authService.getMe()
      .then((user) => {
        setCurrentUser(user);
        setIsAuthenticated(true);
      })
      .catch(() => {
        localStorage.removeItem('auth_token');
        setCurrentUser(null);
        setIsAuthenticated(false);
      })
      .finally(() => {
        setAuthLoading(false);
      });
  }, []);

  if (authLoading) {
    return <div className="p-8 text-center">Loading...</div>;
  }

  if (!isAuthenticated) {
    return (
      <Router>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </Router>
    );
  }

  return (
    <Router>
      <Layout currentUser={currentUser}>
        <Suspense fallback={<div className="p-8 text-center">Loading...</div>}>
          <Routes>
            <Route path="/" element={<Navigate to="/executive-overview" replace />} />
            <Route path="/executive-overview" element={<ExecutiveOverview />} />
            <Route path="/queue-performance" element={<QueuePerformance />} />
            <Route path="/queue-performance-report" element={<QueuePerformanceReport />} />
            <Route path="/agent-performance" element={<AgentPerformance />} />
            <Route path="/agent-performance/:agentId" element={<AgentPerformance />} />
            <Route path="/agent-performance-report" element={<AgentPerformanceReport />} />
            <Route path="/outbound-calls" element={<OutboundCalls />} />
            <Route
              path="/quality-health"
              element={currentUser?.role === 'super_admin' ? <QualityHealth /> : <Navigate to="/executive-overview" replace />}
            />
            <Route path="/repeat-callers" element={<RepeatCallers />} />
            <Route path="/admin/settings" element={<AdminSettings />} />
            <Route path="*" element={<Navigate to="/executive-overview" replace />} />
          </Routes>
        </Suspense>
      </Layout>
    </Router>
  );
}

export default App;
