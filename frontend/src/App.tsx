import React, { Suspense, useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import Login from './pages/Login';
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
const ScheduledReports = React.lazy(() => import('./pages/ScheduledReports'));
const AdminSettings = React.lazy(() => import('./pages/AdminSettings'));
const MetricsAudit = React.lazy(() => import('./pages/MetricsAudit'));

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);

  useEffect(() => {
    const token = localStorage.getItem('auth_token');
    setIsAuthenticated(!!token);
  }, []);

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
      <Layout>
        <Suspense fallback={<div className="p-8 text-center">Loading...</div>}>
          <Routes>
            <Route path="/" element={<ExecutiveOverview />} />
            <Route path="/queue-performance" element={<QueuePerformance />} />
            <Route path="/queue-performance-report" element={<QueuePerformanceReport />} />
            <Route path="/agent-performance" element={<AgentPerformance />} />
            <Route path="/agent-performance/:agentId" element={<AgentPerformance />} />
            <Route path="/agent-performance-report" element={<AgentPerformanceReport />} />
            <Route path="/outbound-calls" element={<OutboundCalls />} />
            <Route path="/quality-health" element={<QualityHealth />} />
            <Route path="/repeat-callers" element={<RepeatCallers />} />
            <Route path="/scheduled-reports" element={<ScheduledReports />} />
            <Route path="/admin/settings" element={<AdminSettings />} />
            <Route path="/admin/metrics-audit" element={<MetricsAudit />} />
          </Routes>
        </Suspense>
      </Layout>
    </Router>
  );
}

export default App;
