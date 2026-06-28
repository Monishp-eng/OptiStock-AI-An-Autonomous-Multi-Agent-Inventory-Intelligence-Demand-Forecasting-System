import React, { useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import {
  LayoutDashboard,
  Package,
  Brain,
  Settings,
  Database,
  Sparkles,
  ShoppingCart,
  Truck,
  ClipboardList,
  LogOut,
  Menu,
  X as CloseIcon,
  Bot,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { useTranslation } from 'react-i18next';
import './Sidebar.css';

function Sidebar() {
  const { logout, user } = useAuth();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [mobileOpen, setMobileOpen] = useState(false);

  // navItems MUST be inside the component so t() re-renders on language change
  const navItems = [
    { path: '/data-input',  icon: Database,        label: t('nav.dataInput') },
    { path: '/dashboard',   icon: LayoutDashboard,  label: t('nav.dashboard') },
    { path: '/inventory',   icon: Package,          label: t('nav.inventory') },
    { path: '/analysis',    icon: Brain,            label: t('nav.analysis') },
    { path: '/sales',       icon: ShoppingCart,     label: t('nav.sales') },
    { path: '/suppliers',   icon: Truck,            label: t('nav.suppliers') },
    { path: '/orders',      icon: ClipboardList,    label: t('nav.orders') },
    { path: '/agent-hub',   icon: Bot,              label: 'Agent Hub', badge: 'NEW' },
    { path: '/settings',    icon: Settings,         label: t('nav.settings') },
  ];

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const closeMobile = () => setMobileOpen(false);

  return (
    <>
      {/* Hamburger button — only visible on mobile */}
      <button className="hamburger-btn" onClick={() => setMobileOpen(o => !o)} aria-label="Toggle menu">
        {mobileOpen ? <CloseIcon size={22} /> : <Menu size={22} />}
      </button>

      {/* Dark overlay — only visible when sidebar is open on mobile */}
      <div
        className={`sidebar-overlay ${mobileOpen ? 'open' : ''}`}
        onClick={closeMobile}
      />

      <aside className={`sidebar ${mobileOpen ? 'sidebar-mobile-open' : ''}`}>
        <div className="sidebar-header">
          <div className="logo">
            <div className="logo-icon-wrapper">
              <Sparkles className="logo-icon" />
            </div>
            <div className="logo-content">
              <span className="logo-text">OptiStock</span>
              <span className="logo-tagline">AI Procurement Agent</span>
            </div>
          </div>
        </div>

        <nav className="sidebar-nav">
          <div className="nav-section">
            <span className="nav-section-title">{t('nav.mainMenu')}</span>
            {navItems.map((item) => (
              <NavLink
                key={item.path}
                to={item.path}
                onClick={closeMobile}
                className={({ isActive }) =>
                  `nav-item ${isActive ? 'active' : ''}`
                }
              >
                <item.icon size={20} />
                <span>{item.label}</span>
                {item.badge && (
                  <span className="nav-badge">{item.badge}</span>
                )}
              </NavLink>
            ))}
          </div>
        </nav>

        <div className="sidebar-footer">
          {user && (
            <div className="sidebar-user">
              <span className="sidebar-username">{user.username}</span>
              <button className="btn-logout" onClick={handleLogout} title="Logout">
                <LogOut size={16} />
                <span>{t('nav.logout')}</span>
              </button>
            </div>
          )}
          <div className="brand-card">
            <span className="brand-text">Powered by</span>
            <span className="brand-name">Google Gemini AI</span>
          </div>
        </div>
      </aside>
    </>
  );
}

export default Sidebar;
