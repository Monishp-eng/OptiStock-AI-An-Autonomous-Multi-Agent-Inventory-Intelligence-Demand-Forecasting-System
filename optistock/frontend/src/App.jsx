import React from 'react';
import { BrowserRouter as Router, Routes, Route, useLocation } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import { AuthProvider } from './context/AuthContext';
import ProtectedRoute from './components/ProtectedRoute';
import Sidebar from './components/Sidebar';
import VoiceAssistant from './components/VoiceAssistant';
import Welcome from './pages/Welcome';
import Dashboard from './pages/Dashboard';
import Inventory from './pages/Inventory';
import DataInput from './pages/DataInput';
import Analysis from './pages/Analysis';
import Settings from './pages/Settings';
import Login from './pages/Login';
import Setup from './pages/Setup';
import SalesEntry from './pages/SalesEntry';
import Suppliers from './pages/Suppliers';
import Orders from './pages/Orders';
import Onboarding from './pages/Onboarding';
import AgentHub from './pages/AgentHub';

// Layout component that conditionally shows sidebar
function Layout({ children }) {
  const location = useLocation();
  const noSidebarPaths = ['/', '/login', '/welcome', '/setup', '/onboarding'];
  const showSidebar = !noSidebarPaths.includes(location.pathname);

  if (!showSidebar) {
    return <>{children}</>;
  }

  return (
    <div className="app">
      <Sidebar />
      <main className="main-content">
        {children}
      </main>
      <VoiceAssistant />
    </div>
  );
}

function App() {
  return (
    <AuthProvider>
      <Router>
        <Layout>
          <Routes>
            {/* Public routes */}
            <Route path="/" element={<Login />} />
            <Route path="/welcome" element={<Welcome />} />
            <Route path="/login" element={<Login />} />
            <Route path="/setup" element={<Setup />} />

            {/* Protected routes */}
            <Route path="/dashboard" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
            <Route path="/inventory" element={<ProtectedRoute><Inventory /></ProtectedRoute>} />
            <Route path="/data-input" element={<ProtectedRoute><DataInput /></ProtectedRoute>} />
            <Route path="/analysis" element={<ProtectedRoute><Analysis /></ProtectedRoute>} />
            <Route path="/settings" element={<ProtectedRoute><Settings /></ProtectedRoute>} />
            <Route path="/sales" element={<ProtectedRoute><SalesEntry /></ProtectedRoute>} />
            <Route path="/suppliers" element={<ProtectedRoute><Suppliers /></ProtectedRoute>} />
            <Route path="/orders" element={<ProtectedRoute><Orders /></ProtectedRoute>} />

            {/* Agent Hub */}
            <Route path="/agent-hub" element={<ProtectedRoute><AgentHub /></ProtectedRoute>} />

            {/* Onboarding */}
            <Route path="/onboarding" element={<ProtectedRoute><Onboarding /></ProtectedRoute>} />
          </Routes>
        </Layout>
        <Toaster
          position="bottom-right"
          toastOptions={{
            duration: 4000,
            style: {
              background: '#1e293b',
              color: '#f8fafc',
              border: '1px solid #334155',
            },
            success: {
              iconTheme: {
                primary: '#10b981',
                secondary: '#f8fafc',
              },
            },
            error: {
              iconTheme: {
                primary: '#ef4444',
                secondary: '#f8fafc',
              },
            },
          }}
        />
      </Router>
    </AuthProvider>
  );
}

export default App;
