import { lazy, Suspense, useState, useSyncExternalStore, type ReactNode } from 'react';
import { authState, subscribeAuth } from '@caf/api-client';
import { BrowserRouter, Routes, Route, NavLink, Link, Navigate, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthGate } from './components/AuthGate';
import { SessionControls } from './components/SessionControls';
import { Diagnostics } from './components/Diagnostics';
import { RouteBoundary } from './components/RouteBoundary';
import { Dialog } from '../../../packages/workspace/Dialog';
import { ThemeControl, useTheme } from '../../../packages/workspace/theme';
const Queue = lazy(() => import('./pages/Queue').then(m => ({ default: m.Queue })));
const ClassificationQueue = lazy(() => import('./pages/ClassificationQueue').then(m => ({ default: m.ClassificationQueue })));
const Extraction = lazy(() => import('./pages/Extraction').then(m => ({ default: m.Extraction })));
const Taxonomy = lazy(() => import('./pages/Taxonomy').then(m => ({ default: m.Taxonomy })));
const TextbookExplorer = lazy(() => import('../../student/src/components/TextbookExplorer').then(m => ({ default: m.TextbookExplorer })));
const TaxonomyRelease = lazy(() => import('./pages/TaxonomyRelease').then(m => ({ default: m.TaxonomyRelease })));
const BulkAccept = lazy(() => import('./pages/BulkAccept').then(m => ({ default: m.BulkAccept })));
const Catalogue = lazy(() => import('./pages/Catalogue').then(m => ({ default: m.Catalogue })));
const Accounts = lazy(() => import('./pages/Accounts').then(m => ({ default: m.Accounts })));
const System = lazy(() => import('./pages/System').then(m => ({ default: m.System })));
const Readiness = lazy(() => import('./pages/Readiness').then(m => ({ default: m.Readiness })));
const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } } });
const navigation = [
  { to: '/classifications', label: 'Review questions' }, { to: '/extraction', label: 'Extraction' },
  { to: '/textbooks', label: 'Syllabus & descriptors' },
];
const administratorNavigation = [
  { to: '/taxonomy-release', label: 'Taxonomy releases' }, { to: '/readiness', label: 'Readiness' }, { to: '/documents', label: 'Source catalogue' }, { to: '/bulk', label: 'Bulk review' },
  { to: '/accounts', label: 'Accounts' }, { to: '/system', label: 'System' },
];
function AdminOnly({ children }: { children: ReactNode }) {
  const state = useSyncExternalStore(subscribeAuth, authState);
  return state.identity?.capabilities.includes('admin') ? <>{children}</> : <section role="alert" className="panel"><h1 className="page-title">Administrator access required.</h1><p>This workflow requires the administrator capability.</p></section>;
}
function CuratorLayout({ children }: { children: ReactNode }) {
  const state = useSyncExternalStore(subscribeAuth, authState);
  const admin = state.identity?.capabilities.includes('admin');
  const [open, setOpen] = useState(false);
  const location = useLocation();
  const title = [...navigation, ...administratorNavigation].find(item => location.pathname.startsWith(item.to))?.label ?? (location.pathname.startsWith('/queue') ? 'Legacy history' : 'Review questions');
  const links = <><nav aria-label="Review navigation" className="curator-navigation">{navigation.map(item => <NavLink key={item.to} to={item.to} onClick={() => setOpen(false)}>{item.label}</NavLink>)}</nav>
    {admin && <nav aria-label="Administration" className="curator-navigation secondary-navigation">{administratorNavigation.map(item => <NavLink key={item.to} to={item.to} onClick={() => setOpen(false)}>{item.label}</NavLink>)}</nav>}
    <details className="workspace-history"><summary>History</summary><nav aria-label="Review history" className="curator-navigation secondary-navigation"><NavLink to="/queue" onClick={() => setOpen(false)}>Legacy history</NavLink><NavLink to="/taxonomy" onClick={() => setOpen(false)}>Legacy taxonomy</NavLink></nav></details></>;
  const account = <details className="account-menu"><summary>Account and settings</summary><div className="curator-account"><Link to="/">Review workspace</Link><a href="/">Study workspace</a><ThemeControl /><SessionControls /><details><summary>Technical details</summary><Diagnostics /></details></div></details>;
  return <div className="curator-workspace"><a href="#main-content" className="skip-link">Skip to content</a><aside className="curator-sidebar"><Link to="/classifications" className="curator-brand">CA Study Companion<span>Shared content review</span></Link>{links}{account}</aside>
    <div className="curator-body"><header className="curator-header"><button className="curator-menu secondary-action" onClick={() => setOpen(true)} aria-haspopup="dialog">Menu</button><span>{title}</span><span className="metadata">{admin ? 'Administrator' : 'Student reviewer'}</span></header>
      <main id="main-content" tabIndex={-1} className="curator-content"><RouteBoundary>{children}</RouteBoundary></main></div>
    <Dialog title="Review navigation" open={open} onClose={() => setOpen(false)} className="curator-navigation-dialog">{links}{account}</Dialog>
  </div>;
}
function Loading() { return <section aria-busy="true" className="panel space-y-4"><p role="status">Loading…</p><div className="skeleton" /><div className="skeleton" /><div className="skeleton" /></section>; }
function CatalogueAlias() { const location = useLocation(); return <Navigate replace to={`/documents${location.search}`} />; }
export function App() {
  useTheme();
  return <QueryClientProvider client={queryClient}><AuthGate><BrowserRouter basename="/curator"><CuratorLayout><Suspense fallback={<Loading />}><Routes>
    <Route path="/" element={<ClassificationQueue />} /><Route path="/classifications" element={<ClassificationQueue />} /><Route path="/queue" element={<Queue />} /><Route path="/extraction" element={<Extraction />} />
    <Route path="/taxonomy" element={<Taxonomy />} /><Route path="/textbooks" element={<TextbookExplorer curator />} /><Route path="/syllabus" element={<TextbookExplorer curator />} />
    <Route path="/readiness" element={<AdminOnly><Readiness /></AdminOnly>} /><Route path="/bulk" element={<AdminOnly><BulkAccept /></AdminOnly>} /><Route path="/documents" element={<AdminOnly><Catalogue /></AdminOnly>} />
    <Route path="/catalog" element={<AdminOnly><CatalogueAlias /></AdminOnly>} /><Route path="/catalogue" element={<AdminOnly><CatalogueAlias /></AdminOnly>} />
    <Route path="/taxonomy-release" element={<AdminOnly><TaxonomyRelease /></AdminOnly>} /><Route path="/accounts" element={<AdminOnly><Accounts /></AdminOnly>} /><Route path="/system" element={<AdminOnly><System /></AdminOnly>} />
    <Route path="*" element={<section className="panel"><h1 className="page-title">Page unavailable</h1><Link to="/classifications">Review questions</Link></section>} />
  </Routes></Suspense></CuratorLayout></BrowserRouter></AuthGate></QueryClientProvider>;
}
export default App;
