import { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { accountKey } from '@caf/api-client';
import { taxonomyApi, type TextbookNode } from '@caf/api-client/src/taxonomy';
import { getData, getTree, mode, usePapers } from '../lib/data';
import { internalReturn, useUrlState } from '../lib/url';
import { demoLink, isDemoMode } from '../lib/demo';
import { PageState } from '../components/PageState';
import { SyllabusTree, type SyllabusNode } from '../components/SyllabusTree';
import { SubtopicDetail } from '../components/SubtopicDetail';
import { TextbookNodeDetail } from '../components/TextbookExplorer';
import type { PaperTree, SubtopicData } from '../lib/contracts';
import { preserveOrigin, restoreOrigin } from '../lib/navigation';
export function paperNodes(tree: PaperTree): SyllabusNode[] {
  if (tree.hierarchy?.length) { const statuses = new Map(tree.chapters.flatMap(ch => ch.topics.flatMap(topic => topic.subtopics)).map(node => [node.id, node.status])); const adapt = (nodes: NonNullable<PaperTree['hierarchy']>): SyllabusNode[] => nodes.map(node => ({ id: node.id, name: node.name, level: node.level, eligible: node.eligible, status: statuses.get(node.id), children: adapt(node.children ?? []) })); return adapt(tree.hierarchy); }
  return tree.chapters.map(ch => ({ id: ch.id, name: ch.name, level: 'chapter', children: ch.topics.map(topic => ({ id: topic.id, name: topic.name, level: 'topic', children: topic.subtopics.map(node => ({ id: node.id, name: node.name, level: 'subtopic', eligible: true, status: node.status, children: [] })) })) }));
}
function locate<T extends { id: string; children?: T[] }>(nodes: T[], id: string): T | undefined { for (const node of nodes) { if (node.id === id) return node; const child = locate(node.children ?? [], id); if (child) return child; } }
export function Syllabus() {
  const { params, set, search } = useUrlState();
  const preview = params.get('preview') === 'draft' || params.get('legacy') === 'true';
  const papers = usePapers();
  const requested = params.get('paper') ?? '';
  const selected = params.get('node') ?? '';
  const paper = papers.data?.find(item => item.id === requested || item.code === requested)?.id ?? papers.data?.[0]?.id ?? '';
  const query = useQuery({ queryKey: ['paper-tree', mode(), paper], enabled: !preview && Boolean(paper), queryFn: () => getTree(paper) });
  const versions = useQuery({ queryKey: ['textbook-versions', accountKey()], enabled: preview && !isDemoMode(), queryFn: taxonomyApi.versions });
  const version = params.get('version') || (params.get('legacy') === 'true' ? versions.data?.find(item => item.status === 'legacy')?.version_id : versions.data?.find(item => item.status !== 'legacy')?.version_id) || '';
  const draft = useQuery({ queryKey: ['textbook-tree', accountKey(), version], enabled: preview && Boolean(version), queryFn: () => taxonomyApi.tree(version) });
  const draftPaper = draft.data?.find(node => node.paper_id === requested || node.paper_id.endsWith(`.${requested}`))?.paper_id ?? draft.data?.[0]?.paper_id ?? '';
  const roots = preview ? (draft.data ?? []).filter(node => node.paper_id === draftPaper) : query.data ? paperNodes(query.data) : [];
  const current = locate<SyllabusNode>(roots as SyllabusNode[], selected);
  const owner = useQuery({ queryKey: ['syllabus-owner', mode(), selected], enabled: !preview && Boolean(selected) && Boolean(query.data) && !current, queryFn: () => getData<SubtopicData>(`/api/v1/subtopics/${encodeURIComponent(selected)}`) });
  useEffect(() => { if (owner.data?.paper && owner.data.paper.id !== paper) set({ paper: owner.data.paper.id }); }, [owner.data, paper]);
  const draftNode = preview ? locate((draft.data ?? []).filter(node => node.paper_id === draftPaper), selected) : undefined;
  const currentPath = `/syllabus${search}`;
  useEffect(() => { if (query.data || draft.data) restoreOrigin(currentPath); }, [query.data, draft.data, currentPath]);
  const awaiting = !preview && query.data?.context && query.data.context.readiness !== 'ready';
  return <div className="space-y-5">{params.get('return') && <Link className="topic-link" to={demoLink(internalReturn(params.get('return'), '/syllabus'))}>← Return</Link>}<h1 className="page-title">Syllabus</h1><p>Explore your official syllabus and open a topic to study questions, notes and references.</p>{preview && <p className="card" role="status"><strong>Draft—awaiting review</strong> · Preview only. Attempt applicability and personal progress are unavailable.</p>}{awaiting && <p className="card">The syllabus for this attempt is awaiting review. <Link className="topic-link" to={demoLink('/syllabus?preview=draft')}>Preview draft syllabus</Link> · <Link className="topic-link" to="/progress?tab=coverage">View readiness</Link></p>}
    <PageState loading={preview ? !isDemoMode() && (versions.isPending || draft.isLoading) : papers.isPending || query.isLoading} refreshing={query.isFetching && Boolean(query.data)} error={preview ? versions.error ?? draft.error : papers.error ?? query.error ?? owner.error} retry={() => { papers.refetch(); query.refetch(); versions.refetch(); draft.refetch(); owner.refetch(); }} />
    {preview && versions.data?.length ? <label className="block">Taxonomy version <select aria-label="Taxonomy version" value={version} onChange={event => set({ version:event.target.value,node:'' })}>{versions.data.map(item => <option key={item.version_id} value={item.version_id}>{item.version_id} · {item.status}</option>)}</select></label> : null}
    <div className={`syllabus-columns ${current ? 'syllabus-has-detail' : ''}`}><section className="card syllabus-tree-pane"><div className="space-y-3"><label className="block">Paper <select aria-label="Paper" className="w-full" value={preview ? draftPaper : paper} onChange={event => set({ paper: event.target.value, node: '', search: '', status: '' })}>{preview ? [...new Map((draft.data ?? []).map(node => [node.paper_id, node.name])).entries()].map(([id, name]) => <option key={id} value={id}>{name}</option>) : papers.data?.map(item => <option key={item.id} value={item.id}>{item.code} — {item.name}</option>)}</select></label><label className="block">Search syllabus <input className="w-full" value={params.get('search') ?? ''} onChange={event => set({ search: event.target.value })} /></label>{!preview && <label className="block">Status <select aria-label="Status" value={params.get('status') ?? 'all'} onChange={event => set({ status: event.target.value })}><option value="all">All</option><option value="not_started">Not started</option><option value="in_progress">In progress</option><option value="done">Done</option></select></label>}<SyllabusTree nodes={roots as SyllabusNode[]} selected={selected} search={params.get('search') ?? ''} status={params.get('status') ?? 'all'} scope={`${mode()}:${preview ? version : paper}`} select={node => { preserveOrigin(currentPath, `tree-${node.id}`); set({ node: node.id }); }} /></div>{!roots.length && !query.isPending && !draft.isLoading && <p>No approved topics are available. <Link className="topic-link" to="/syllabus?preview=draft">Preview draft syllabus</Link></p>}</section><section className="min-w-0">{current ? <><button className="mobile-only topic-link mb-4" onClick={() => set({ node: '' })}>← Back to syllabus</button>{draftNode ? <TextbookNodeDetail node={draftNode as TextbookNode} version={version} curator={false} /> : <SubtopicDetail key={selected} paperId={paper} nodeId={selected} />}</> : <p className="card">Select a topic from the syllabus.</p>}</section></div>
  </div>;
}
