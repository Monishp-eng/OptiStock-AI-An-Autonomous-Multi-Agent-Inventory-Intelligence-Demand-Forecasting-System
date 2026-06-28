/**
 * ProtectedRoute.jsx — Guards routes that require authentication.
 *
 * Shows a spinner while AuthContext is loading (prevents redirect on refresh).
 * Redirects to /login only after loading=false AND isAuthenticated=false.
 */
import React from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export default function ProtectedRoute({ children }) {
  const { isAuthenticated, loading } = useAuth();

  if (loading) {
    return (
      <div className="auth-loading">
        <div className="auth-loading-spinner" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return children;
}
