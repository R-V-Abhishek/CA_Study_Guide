import { Navigate, useParams, useSearchParams } from 'react-router-dom';
import { demoLink } from '../lib/demo';
/** Existing paper/topic bookmarks open the same syllabus workspace. */
export function PaperDetail() {
  const { paperId='',nodeId }=useParams();
  const [params]=useSearchParams();
  const next=new URLSearchParams(params);next.set('paper',paperId);if (nodeId) next.set('node',nodeId);else next.delete('node');
  return <Navigate replace to={demoLink(`/syllabus?${next}`)} />;
}
