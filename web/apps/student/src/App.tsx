import { lazy, Suspense, useState, type ReactNode } from 'react';
import { createBrowserRouter, RouterProvider, Routes, Route, NavLink, Link, Navigate, useLocation } from 'react-router-dom';
import { BookOpen, Calendar, RotateCcw, BarChart3, FileCheck, Menu, Search, MoreHorizontal, Home, ListTree } from 'lucide-react';
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import { accountKey, apiRequest, type components } from '@caf/api-client';
import { isDemoMode, demoLink } from './lib/demo';
import { RouteBoundary } from './components/RouteBoundary';
import { Diagnostics } from './components/Diagnostics';
import { AuthGate } from './components/AuthGate';
import { SessionControls } from './components/SessionControls';
import { Dialog } from '../../../packages/workspace/Dialog';
import { ThemeControl, useTheme } from '../../../packages/workspace/theme';

const Dashboard = lazy(() => import('./pages/Dashboard').then(m => ({ default: m.Dashboard })));
const Papers = lazy(() => import('./pages/Papers').then(m => ({ default: m.Papers })));
const PaperDetail = lazy(() => import('./pages/PaperDetail').then(m => ({ default: m.PaperDetail })));
const Syllabus = lazy(() => import('./pages/Syllabus').then(m => ({ default: m.Syllabus })));
const Plan = lazy(() => import('./pages/Plan').then(m => ({ default: m.Plan })));
const Revision = lazy(() => import('./pages/Revision').then(m => ({ default: m.Revision })));
const Progress = lazy(() => import('./pages/Progress').then(m => ({ default: m.Progress })));
const Profile = lazy(() => import('./pages/Profile').then(m => ({ default: m.Profile })));
const MockTests = lazy(() => import('./pages/MockTests').then(m => ({ default: m.MockTests })));
const Questions = lazy(() => import('./pages/Questions').then(m => ({ default: m.Questions })));
const QuestionReader = lazy(() => import('./pages/QuestionReader').then(m => ({ default: m.QuestionReader })));
const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 120_000, refetchOnWindowFocus: false } } });
const primary = [
  { to: '/', label: 'Today', icon: Home }, { to: '/papers', label: 'Papers', icon: BarChart3 },
  { to: '/syllabus', label: 'Syllabus', icon: ListTree }, { to: '/questions', label: 'Questions', icon: BookOpen },
  { to: '/plan', label: 'Plan', icon: Calendar }, { to: '/revision', label: 'Revision', icon: RotateCcw },
];
const secondary = [{ to: '/progress', label: 'Progress', icon: BarChart3 }, { to: '/mock', label: 'Mock results', icon: FileCheck }];
function Navigation({ close }: { close?: () => void }) {
  return <><nav aria-label="Study navigation" className="workspace-navigation">{primary.map(item => <NavLink end={item.to === '/'} to={demoLink(item.to)} key={item.to} onClick={close}><item.icon size={18} aria-hidden="true" />{item.label}</NavLink>)}</nav>
    <nav aria-label="Study records" className="workspace-navigation secondary-navigation">{secondary.map(item => <NavLink to={demoLink(item.to)} key={item.to} onClick={close}><item.icon size={18} aria-hidden="true" />{item.label}</NavLink>)}</nav></>;
}
function AccountArea({ close }: { close?: () => void }) {
  return <div className="workspace-account"><Link to={demoLink('/profile')} onClick={close}>Profile and settings</Link><ThemeControl />
    {!isDemoMode() && <SessionControls />}<a href="/curator/classifications">Review shared content</a><details><summary>Technical details</summary><Diagnostics /></details></div>;
}
function ShellContext() {
  const demo = isDemoMode();
  const query = useQuery({ queryKey: ['settings', accountKey()], queryFn: () => apiRequest<components['schemas']['ProfileSettings']>('/api/v1/me/settings'), enabled: !demo });
  if (demo) return <span className="metadata">Demo attempt · Demo papers</span>;
  if (query.isPending) return <span className="metadata" aria-busy="true">Loading study context…</span>;
  if (!query.data) return <Link className="metadata" to="/profile">Set your exam target</Link>;
  const settings = query.data;
  const label = settings.available_attempts.find(a => a.id === settings.target_attempt_id)?.label ?? settings.target_attempt_id;
  const papers = settings.available_papers.filter(p => settings.selected_paper_ids.includes(p.id));
  return <span className="metadata shell-context">{label}<span>{papers.length ? papers.map(p => p.code).join(', ') : 'No papers selected'}</span></span>;
}
function Layout({ children }: { children: ReactNode }) {
  const location = useLocation();
  const [menu, setMenu] = useState<'navigation' | 'more' | null>(null);
  const title = [...primary, ...secondary].find(item => item.to === '/' ? location.pathname === '/' : location.pathname.startsWith(item.to))?.label ?? (location.pathname.startsWith('/profile') ? 'Settings' : 'Syllabus');
  return <div className="student-workspace"><a href="#main-content" className="skip-link">Skip to content</a>
    <aside className="workspace-sidebar"><Link to={demoLink('/')} className="workspace-brand"><BookOpen size={22} aria-hidden="true" />CA Final Prep</Link><Navigation /><AccountArea /></aside>
    <div className="workspace-body"><header className="workspace-header"><button className="tablet-menu secondary-action" onClick={() => setMenu('navigation')}><Menu size={18} aria-hidden="true" />Menu</button>
      <span className="shell-page-name">{title}</span><ShellContext />{isDemoMode() && <span className="status-label">Demo Mode</span>}
      <Link className="secondary-action shell-search" to={demoLink('/questions')}><Search size={18} aria-hidden="true" /><span>Search questions</span></Link>
    </header><main id="main-content" tabIndex={-1} className="workspace-content">{children}</main></div>
    <nav aria-label="Mobile study navigation" className="mobile-navigation">{primary.filter(item => ['/', '/syllabus', '/questions', '/plan'].includes(item.to)).map(item => <NavLink end={item.to === '/'} to={demoLink(item.to)} key={item.to}><item.icon size={18} aria-hidden="true" /><span>{item.label}</span></NavLink>)}<button onClick={() => setMenu('more')} aria-haspopup="dialog"><MoreHorizontal size={18} aria-hidden="true" /><span>More</span></button></nav>
    <Dialog open={menu !== null} onClose={() => setMenu(null)} title={menu === 'more' ? 'More destinations' : 'Study navigation'} className="navigation-dialog">
      {menu === 'more' ? <nav className="workspace-navigation" aria-label="More destinations">{[primary[1], primary[5], ...secondary].map(item => <NavLink to={demoLink(item.to)} key={item.to} onClick={() => setMenu(null)}>{item.label}</NavLink>)}</nav> : <Navigation close={() => setMenu(null)} />}<AccountArea close={() => setMenu(null)} />
    </Dialog>
  </div>;
}
function DraftRedirect() {
  const location = useLocation(); const params = new URLSearchParams(location.search); params.set('preview', 'draft');
  return <Navigate replace to={`/syllabus?${params}`} />;
}
function PageLoading() {
  return <section aria-busy="true" aria-label="Loading page" className="space-y-4"><p role="status">Loading…</p><div className="skeleton w-1/2" /><div className="card space-y-4"><div className="skeleton" /><div className="skeleton" /><div className="skeleton w-2/3" /></div></section>;
}
const router = createBrowserRouter([{ path: '*', element: <Layout><RouteBoundary><Suspense fallback={<PageLoading />}><Routes>
  <Route path="/" element={<Dashboard />} /><Route path="/papers" element={<Papers />} /><Route path="/papers/:paperId" element={<PaperDetail />} /><Route path="/papers/:paperId/:nodeId" element={<PaperDetail />} />
  <Route path="/syllabus" element={<Syllabus />} /><Route path="/textbooks" element={<DraftRedirect />} /><Route path="/questions" element={<Questions />} /><Route path="/questions/:questionId" element={<QuestionReader />} />
  <Route path="/plan" element={<Plan />} /><Route path="/revision" element={<Revision />} /><Route path="/progress" element={<Progress />} /><Route path="/profile" element={<Profile />} /><Route path="/mock" element={<MockTests />} />
  <Route path="*" element={<section className="card"><h1 className="page-title">Page unavailable</h1><Link className="topic-link" to={demoLink('/')}>Return to Today</Link></section>} />
</Routes></Suspense></RouteBoundary></Layout> }]);
export function App() { useTheme(); return <QueryClientProvider client={queryClient}><AuthGate demo={isDemoMode()}><RouterProvider router={router} /></AuthGate></QueryClientProvider>; }
export default App;
