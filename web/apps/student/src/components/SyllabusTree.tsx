import { useEffect, useMemo, useRef, useState } from 'react';
import { readNavigation, writeNavigation } from '../lib/navigation';
export interface SyllabusNode { id: string; name: string; level: string; children: SyllabusNode[]; status?: string; eligible?: boolean }
export function SyllabusTree({ nodes, selected, search, status, scope, select }: { nodes: SyllabusNode[]; selected: string; search: string; status: string; scope: string; select: (node: SyllabusNode) => void }) {
  const [expanded, setExpanded] = useState<string[]>(() => readNavigation(`tree:${scope}`, nodes.map(node => node.id)));
  const [focused, setFocused] = useState(selected || nodes[0]?.id || '');
  const pane = useRef<HTMLDivElement>(null);
  useEffect(() => { setExpanded(readNavigation(`tree:${scope}`, nodes.map(node => node.id))); }, [scope]);
  useEffect(() => { writeNavigation(`tree:${scope}`, expanded); }, [scope, expanded]);
  useEffect(() => {
    const path: string[] = [];
    function locate(items: SyllabusNode[]): boolean { for (const node of items) { if (node.id === selected) return true; if (locate(node.children)) { path.push(node.id); return true; } } return false; }
    if (selected && locate(nodes)) setExpanded(previous => path.some(id => !previous.includes(id)) ? [...new Set([...previous, ...path])] : previous);
  }, [selected, scope, nodes]);
  const activeFilter = Boolean(search.trim()) || status !== 'all';
  const filtered = useMemo(() => {
    function prune(items: SyllabusNode[], ancestorMatch = false): SyllabusNode[] {
      return items.flatMap(node => { const matched = ancestorMatch || !search.trim() || node.name.toLowerCase().includes(search.trim().toLowerCase()); const children = prune(node.children, matched && Boolean(search.trim())); const leafMatch = !node.children.length && matched && (status === 'all' || node.status === status); return children.length || leafMatch ? [{ ...node, children }] : []; });
    }
    return activeFilter ? prune(nodes) : nodes;
  }, [nodes, search, status, activeFilter]);
  const visible: { node: SyllabusNode; depth: number; parent?: string }[] = [];
  function flatten(items: SyllabusNode[], depth = 0, parent?: string) { for (const node of items) { visible.push({ node, depth, parent }); if (activeFilter || expanded.includes(node.id)) flatten(node.children, depth + 1, node.id); } }
  flatten(filtered);
  const toggle = (id: string) => setExpanded(previous => previous.includes(id) ? previous.filter(value => value !== id) : [...previous, id]);
  const focus = (id: string) => { setFocused(id); requestAnimationFrame(() => document.getElementById(`tree-${id}`)?.focus()); };
  useEffect(() => { if (visible.length && !visible.some(row => row.node.id === focused)) setFocused(visible[0].node.id); }, [visible.map(row => row.node.id).join('|'), focused]);
  return <div ref={pane}><div className="controls"><button type="button" disabled={!nodes.length} onClick={() => { const ids: string[] = []; const walk = (items: SyllabusNode[]) => items.forEach(node => { if (node.children.length) ids.push(node.id); walk(node.children); }); walk(nodes); setExpanded(ids); }}>Expand to topics</button><button type="button" disabled={!nodes.length} onClick={() => setExpanded([])}>Collapse all</button></div><div role="tree" aria-label="Syllabus hierarchy" className="syllabus-tree">{visible.map(({ node, depth, parent }, index) => <div key={node.id} id={`tree-${node.id}`} role="treeitem" aria-level={depth + 1} aria-selected={selected === node.id} aria-expanded={node.children.length ? activeFilter || expanded.includes(node.id) : undefined} tabIndex={focused === node.id ? 0 : -1} style={{ paddingLeft: 12 + depth * 20 }} onFocus={() => setFocused(node.id)} onClick={() => node.children.length ? toggle(node.id) : select(node)} onKeyDown={event => {
    if (['ArrowDown', 'ArrowUp', 'ArrowLeft', 'ArrowRight', 'Home', 'End', 'Enter', ' '].includes(event.key)) event.preventDefault();
    if (event.key === 'ArrowDown') focus(visible[Math.min(index + 1, visible.length - 1)].node.id);
    if (event.key === 'ArrowUp') focus(visible[Math.max(index - 1, 0)].node.id);
    if (event.key === 'Home') focus(visible[0].node.id);
    if (event.key === 'End') focus(visible[visible.length - 1].node.id);
    if (event.key === 'ArrowRight' && node.children.length) { if (!expanded.includes(node.id)) toggle(node.id); else focus(node.children[0].id); }
    if (event.key === 'ArrowLeft') { if (expanded.includes(node.id)) toggle(node.id); else if (parent) focus(parent); }
    if (event.key === 'Enter' || event.key === ' ') { if (node.children.length) toggle(node.id); else select(node); }
  }}><span aria-hidden="true">{node.children.length ? activeFilter || expanded.includes(node.id) ? '▾' : '▸' : '·'}</span><span>{node.name}{node.status && <span className="study-meta block">{node.status.replace(/_/g, ' ')}</span>}</span></div>)}</div>{!visible.length && <p>No topics match these filters.</p>}</div>;
}
