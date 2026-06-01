import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { onAuthStateChange, getSession } from './lib/supabase';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Results from './pages/Results';

// Protected Route component
const ProtectedRoute = ({ children }) => {
  const [isAuthenticated, setIsAuthenticated] = useState(null);

  useEffect(() => {
    checkAuth();
  }, []);

  const checkAuth = async () => {
    const session = await getSession();
    setIsAuthenticated(!!session);
  };

  if (isAuthenticated === null) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="w-8 h-8 border-4 border-blue-600 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return isAuthenticated ? children : <Navigate to="/login" />;
};

function App() {
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    // Listen for auth state changes
    const { data: authListener } = onAuthStateChange(() => {
      setIsLoading(false);
    });

    // Initial check
    getSession().then(() => setIsLoading(false));

    return () => {
      authListener?.subscription?.unsubscribe();
    };
  }, []);

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="w-8 h-8 border-4 border-blue-600 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <Router>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <Dashboard />
            </ProtectedRoute>
          }
        />
        <Route
          path="/results/:contractId"
          element={
            <ProtectedRoute>
              <Results />
            </ProtectedRoute>
          }
        />
        <Route path="*" element={<Navigate to="/" />} />
      </Routes>
    </Router>
  );
}

export default App;
