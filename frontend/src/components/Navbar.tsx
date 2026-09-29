import React from 'react';
import { Briefcase, LayoutGrid, Globe, BarChart2, Shield, LogIn, LogOut, Sparkles, Lock, Compass } from 'lucide-react';
import type { User } from '../api/client';

type Tab = 'board' | 'ai-jobs' | 'explore' | 'scraper' | 'analytics' | 'security';

interface NavbarProps {
  activeTab: Tab;
  setActiveTab: (t: Tab) => void;
  user: User | null;
  isDemoMode: boolean;
  onToggleDemoMode: () => void;
  onOpenAuth: () => void;
  onLogout: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  activeTab,
  setActiveTab,
  user,
  isDemoMode,
  onToggleDemoMode,
  onOpenAuth,
  onLogout,
}) => {
  const tabs: { id: Tab; label: string; Icon: React.ElementType; requiresAuth?: boolean }[] = [
    { id: 'board', label: 'Board', Icon: LayoutGrid },
    { id: 'ai-jobs', label: 'AI Found Jobs', Icon: Sparkles },
    { id: 'explore', label: 'Explore Jobs', Icon: Compass, requiresAuth: true },
    { id: 'scraper', label: 'URL Scraper', Icon: Globe },
    { id: 'analytics', label: 'Analytics', Icon: BarChart2 },
    { id: 'security', label: 'Security', Icon: Shield, requiresAuth: true },
  ];

  return (
    <header className="app-navbar" style={{
      background: 'rgba(8, 12, 24, 0.75)',
      backdropFilter: 'blur(20px)',
      WebkitBackdropFilter: 'blur(20px)',
      borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
      padding: '0 24px',
      position: 'sticky',
      top: 0,
      zIndex: 100,
      boxShadow: '0 8px 32px rgba(0, 0, 0, 0.6)',
    }}>
      <div className="app-navbar-inner" style={{
        maxWidth: 1300,
        margin: '0 auto',
        display: 'flex',
        alignItems: 'center',
        height: 64,
        gap: 20,
      }}>

        {/* Brand Logo */}
        <div
          className="app-navbar-brand"
          style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', flexShrink: 0 }}
          onClick={() => setActiveTab('board')}
        >
          <div style={{
            width: 36, height: 36, borderRadius: 12,
            background: 'linear-gradient(135deg, #6366f1 0%, #ec4899 100%)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            boxShadow: '0 0 20px rgba(99, 102, 241, 0.5)',
          }}>
            <Briefcase size={19} color="#fff" />
          </div>
          <span style={{
            fontFamily: 'var(--font-heading)',
            fontWeight: 800,
            fontSize: '1.2rem',
            background: 'linear-gradient(135deg, #ffffff 0%, #cbd5e1 100%)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            letterSpacing: '-0.02em',
          }}>
            JobPilot
          </span>
        </div>

        {/* Divider */}
        <div className="app-navbar-divider" style={{ width: 1, height: 26, background: 'rgba(255, 255, 255, 0.1)', flexShrink: 0 }} />

        {/* Nav Tabs */}
        <nav className="app-navbar-tabs" style={{ display: 'flex', gap: 6, flex: 1, alignItems: 'center' }}>
          {tabs.map(({ id, label, Icon, requiresAuth }) => {
            const isLocked = requiresAuth && !user;
            const isActive = activeTab === id;

            return (
              <button
                key={id}
                onClick={() => setActiveTab(id)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 8,
                  padding: '8px 16px',
                  borderRadius: 10,
                  border: 'none',
                  cursor: 'pointer',
                  fontSize: '0.86rem',
                  fontWeight: isActive ? 700 : 500,
                  transition: 'all 0.2s cubic-bezier(0.16, 1, 0.3, 1)',
                  background: isActive ? 'linear-gradient(135deg, rgba(99, 102, 241, 0.22) 0%, rgba(236, 72, 153, 0.15) 100%)' : 'transparent',
                  color: isActive ? '#ffffff' : isLocked ? '#64748b' : '#94a3b8',
                  boxShadow: isActive ? '0 0 16px rgba(99, 102, 241, 0.25)' : 'none',
                  borderBottom: isActive ? '2px solid #6366f1' : '2px solid transparent',
                }}
              >
                <Icon size={16} color={isActive ? '#38bdf8' : 'currentColor'} />
                {label}
                {isLocked && <Lock size={12} style={{ color: '#64748b', marginLeft: 2 }} />}
              </button>
            );
          })}
        </nav>

        {/* Demo Mode Toggle Badge (Only for unauthenticated outsiders) */}
        {!user && (
          <button
            onClick={onToggleDemoMode}
            title={isDemoMode ? "Click to disable Demo Mode" : "Click to enable Demo Mode with sample data"}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '5px 14px',
              borderRadius: 99,
              border: isDemoMode ? '1px solid rgba(251, 191, 36, 0.4)' : '1px solid rgba(255, 255, 255, 0.1)',
              background: isDemoMode ? 'rgba(251, 191, 36, 0.12)' : 'rgba(255, 255, 255, 0.04)',
              color: isDemoMode ? '#fbbf24' : '#94a3b8',
              fontSize: '0.78rem',
              fontWeight: 700,
              cursor: 'pointer',
              transition: 'all 0.2s ease',
              boxShadow: isDemoMode ? '0 0 18px rgba(251, 191, 36, 0.25)' : 'none',
              flexShrink: 0,
            }}
          >
            <Sparkles size={14} color={isDemoMode ? '#fbbf24' : '#64748b'} />
            <span>{isDemoMode ? 'DEMO MODE ON' : 'Try Demo Mode'}</span>
          </button>
        )}

        {/* User section */}
        {user ? (
          <div className="app-navbar-account" style={{ display: 'flex', alignItems: 'center', gap: 12, flexShrink: 0 }}>
            <span title={user.username} style={{ fontSize: '0.86rem', color: '#ffffff', fontWeight: 600 }}>
              {user.username}
            </span>
            <button className="btn btn-secondary" onClick={onLogout} style={{ padding: '6px 14px', fontSize: '0.8rem' }}>
              <LogOut size={14} /> Sign out
            </button>
          </div>
        ) : (
          <button className="btn btn-primary" onClick={onOpenAuth} style={{ padding: '8px 20px', fontSize: '0.86rem', flexShrink: 0 }}>
            <LogIn size={15} /> Sign in
          </button>
        )}
      </div>
    </header>
  );
};
