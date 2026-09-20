import React from 'react';
import type { EnrichedApplication } from '../api/client';
import { Briefcase, TrendingUp, Award, XCircle, BarChart2, Activity } from 'lucide-react';

interface AnalyticsProps {
  applications: EnrichedApplication[];
}

export const AnalyticsDashboard: React.FC<AnalyticsProps> = ({ applications }) => {
  const total = applications.length;
  const count = (s: string) => applications.filter(a => a.status === s).length;

  const applied = count('APPLIED');
  const interviewing = count('INTERVIEWING');
  const offered = count('OFFERED');
  const rejected = count('REJECTED');
  const withdrawn = count('WITHDRAWN');

  const interviewRate = total > 0 ? ((interviewing / total) * 100).toFixed(1) : '0';
  const offerRate = total > 0 ? ((offered / total) * 100).toFixed(1) : '0';

  const stats = [
    { label: 'Total Tracked', value: total, icon: Briefcase, color: '#38bdf8', glow: 'rgba(56, 189, 248, 0.25)' },
    { label: 'Interview Rate', value: `${interviewRate}%`, icon: TrendingUp, color: '#fbbf24', glow: 'rgba(251, 191, 36, 0.25)' },
    { label: 'Offer Rate', value: `${offerRate}%`, icon: Award, color: '#34d399', glow: 'rgba(52, 211, 153, 0.25)' },
    { label: 'Rejected', value: rejected, icon: XCircle, color: '#fb7185', glow: 'rgba(251, 113, 133, 0.25)' },
  ];

  const pipeline = [
    { label: 'Applied', count: applied, color: '#38bdf8' },
    { label: 'Interviewing', count: interviewing, color: '#fbbf24' },
    { label: 'Offered', count: offered, color: '#34d399' },
    { label: 'Rejected', count: rejected, color: '#fb7185' },
    { label: 'Withdrawn', count: withdrawn, color: '#c084fc' },
  ];

  return (
    <div style={{ padding: '24px 0 40px' }}>

      {/* KPI Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 18, marginBottom: 24 }}>
        {stats.map(({ label, value, icon: Icon, color, glow }) => (
          <div
            key={label}
            className="acrylic-card acrylic-card-hover"
            style={{
              padding: 22,
              borderTop: `3px solid ${color}`,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
              <span style={{ fontSize: '0.82rem', color: 'var(--text-muted)', fontWeight: 600 }}>{label}</span>
              <div style={{
                width: 38, height: 38, borderRadius: 12,
                background: glow,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                boxShadow: `0 0 16px ${glow}`,
              }}>
                <Icon size={19} color={color} />
              </div>
            </div>
            <div style={{ fontFamily: 'var(--font-heading)', fontSize: '2.2rem', fontWeight: 800, color: '#ffffff' }}>
              {value}
            </div>
          </div>
        ))}
      </div>

      {/* Pipeline breakdown + Recent Activity */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 0.8fr', gap: 20 }}>

        {/* Pipeline Bar Chart */}
        <div className="acrylic-card" style={{ padding: 26 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 24 }}>
            <BarChart2 size={20} color="#38bdf8" />
            <h3 style={{ fontSize: '1.05rem', fontWeight: 700, color: '#ffffff' }}>Application Pipeline Breakdown</h3>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
            {pipeline.map(({ label, count, color }) => (
              <div key={label}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.84rem', marginBottom: 6 }}>
                  <span style={{ color: 'var(--text-body)', fontWeight: 600 }}>{label}</span>
                  <span style={{ fontWeight: 800, color: '#ffffff' }}>
                    {count} <span style={{ fontSize: '0.76rem', color: 'var(--text-dim)' }}>({total > 0 ? ((count / total) * 100).toFixed(0) : 0}%)</span>
                  </span>
                </div>
                <div style={{ height: 8, background: 'var(--bg-inset)', borderRadius: 99, overflow: 'hidden', border: '1px solid var(--border-glass)' }}>
                  <div style={{
                    height: '100%',
                    width: `${total > 0 ? (count / total) * 100 : 0}%`,
                    background: color,
                    borderRadius: 99,
                    boxShadow: `0 0 12px ${color}`,
                    transition: 'width 0.5s cubic-bezier(0.16, 1, 0.3, 1)',
                  }} />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Recent Activity Stream */}
        <div className="acrylic-card" style={{ padding: 26 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
            <Activity size={20} color="#c084fc" />
            <h3 style={{ fontSize: '1.05rem', fontWeight: 700, color: '#ffffff' }}>Recent Activity Stream</h3>
          </div>

          {applications.length === 0 ? (
            <p style={{ color: 'var(--text-dim)', fontSize: '0.86rem' }}>No application activity recorded.</p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {applications.slice(0, 6).map(app => (
                <div key={app.id} style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  padding: '12px 14px', background: 'var(--bg-inset)', borderRadius: 'var(--radius-sm)',
                  border: '1px solid var(--border-glass)',
                }}>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: '0.86rem', fontWeight: 700, color: '#ffffff', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {app.job?.title || `Job #${app.job_id}`}
                    </div>
                    <div style={{ fontSize: '0.76rem', color: 'var(--text-muted)' }}>
                      {app.company?.name || '—'}
                    </div>
                  </div>
                  <span className={`status-pill status-${app.status}`} style={{ fontSize: '0.68rem', padding: '2px 8px' }}>
                    {app.status}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
