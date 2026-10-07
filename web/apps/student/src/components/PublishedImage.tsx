import { useEffect, useState } from 'react';
import { authenticatedFetch } from '@caf/api-client';
import { PageState } from './PageState';

/** Assets are fetched through the authenticated published-content boundary. */
export function PublishedImage({ url, label }: { url: string; label: string }) {
  const [image, setImage] = useState('');
  const [error, setError] = useState<Error | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    let objectUrl = '';
    setImage(''); setError(null);
    const load = async () => {
      try {
        if (!/^\/api\/v1\/published-(sources|assets)\//.test(url)) throw new Error('Published image reference unavailable.');
        const response = await authenticatedFetch(url, { signal: controller.signal });
        if (!response.ok) throw new Error(`Source image unavailable (${response.status}).`);
        const blob = await response.blob();
        if (controller.signal.aborted) return;
        objectUrl = URL.createObjectURL(blob); setImage(objectUrl);
      } catch (error) { if (!controller.signal.aborted) setError(error instanceof Error ? error : new Error('Image unavailable.')); }
    };
    void load();
    return () => { controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [url]);
  return <div><PageState loading={!image && !error} error={error} />{image && <img className="max-w-full rounded border" src={image} alt={label} />}</div>;
}
