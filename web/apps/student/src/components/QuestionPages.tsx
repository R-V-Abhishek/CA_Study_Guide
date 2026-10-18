import { useState } from 'react';
import type { PublishedQuestionPage } from '@caf/api-client';
import { PublishedImage } from './PublishedImage';

export function QuestionPages({ pages, label, revision }: { pages: PublishedQuestionPage[]; label: string; revision: number }) {
  const [crop, setCrop] = useState(false);
  return <section className="space-y-5" aria-label={`${label} source pages`}>
    <div className="controls"><label><input type="checkbox" checked={crop} onChange={event => setCrop(event.target.checked)} /> Focus on relevant question area</label></div>
    <p className="study-meta">Original pages preserve tables and formatting. A green marker identifies the recorded question start where its location is known. Focus is optional; use the full page to check surrounding context.</p>
    {pages.map((page, index) => <figure className="source-question-page space-y-2" key={`${page.source_id}:${page.page}`}>
      <PublishedImage url={`${page.url}${crop ? '' : '?crop=false'}`} label={`${label}, source page ${page.page}`} eager={index === 0} revision={revision} enlarge />
      <figcaption className="study-meta">{label} · Source page {page.page}</figcaption>
    </figure>)}
  </section>;
}
