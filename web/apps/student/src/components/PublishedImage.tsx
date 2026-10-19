import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { accountKey, authenticatedFetch } from '@caf/api-client';
import { PageState } from './PageState';
import { Dialog } from '../../../../packages/workspace/Dialog';

/** Private blobs live only in the account-scoped query cache, never browser storage. */
export function PublishedImage({ url, label, enlarge = false, eager = false, revision }: { url: string; label: string; enlarge?: boolean; eager?: boolean; revision?: number }) {
  const container = useRef<HTMLDivElement>(null);
  const [near, setNear] = useState(eager);
  const [image, setImage] = useState('');
  const [expanded, setExpanded] = useState(false);
  useEffect(() => {
    if (near) return;
    const observer = new IntersectionObserver(entries => {
      if (entries.some(entry => entry.isIntersecting)) { setNear(true); observer.disconnect(); }
    }, { rootMargin: '400px' });
    if (container.current) observer.observe(container.current);
    return () => observer.disconnect();
  }, [near]);
  const query = useQuery({
    queryKey: ['published-image', accountKey(), revision, url], enabled: near,
    staleTime: 5 * 60_000, gcTime: 60_000, retry: false,
    queryFn: async ({ signal }) => {
      const published = /^\/api\/v1\/published-(sources|assets)\//.test(url);
      const questionPage = /^\/api\/v1\/questions\/[^/?#]+\/pages\/(question|answer)\/\d+\/\d+(\?crop=(true|false))?$/.test(url);
      if (!published && !questionPage) throw new Error('Published image reference unavailable.');
      const response = await authenticatedFetch(url, { signal });
      if (!response.ok) throw new Error(`Source image unavailable (${response.status}).`);
      return response.blob();
    },
  });
  useEffect(() => {
    setImage('');
    if (!query.data) return;
    const objectUrl = URL.createObjectURL(query.data);
    setImage(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [query.data]);
  return <div ref={container} className="published-image">
    {!near && <div className="source-page-placeholder study-meta">{label} · Loads when nearby</div>}
    <PageState loading={near && !image && !query.error} error={query.error} retry={() => query.refetch()} />
    {image && <><img className="max-w-full rounded border" src={image} alt={label} decoding="async" />
      {enlarge && <button className="secondary-action" onClick={() => setExpanded(true)}>Enlarge image</button>}
      <Dialog open={expanded} title={label} className="image-enlargement" onClose={() => setExpanded(false)}><div className="image-enlargement-canvas" tabIndex={0} role="region" aria-label="Full-size source image"><img src={image} alt={label} /></div></Dialog></>}
  </div>;
}
