import type { PaperTree } from './contracts';
import type { SyllabusNode } from '../components/SyllabusTree';
/** Keep the official hierarchy intact; the chapter projection supplies personal status. */
export function paperNodes(tree: PaperTree): SyllabusNode[] {
  if (tree.hierarchy?.length) {
    const statuses=new Map(tree.chapters.flatMap(chapter => chapter.topics.flatMap(topic => topic.subtopics)).map(node => [node.id,node.status]));
    const adapt=(nodes:NonNullable<PaperTree['hierarchy']>):SyllabusNode[] => nodes.map(node => ({ id:node.id,name:node.name,level:node.level,eligible:node.eligible,status:statuses.get(node.id),children:adapt(node.children ?? []) }));
    return adapt(tree.hierarchy);
  }
  return tree.chapters.map(chapter => ({ id:chapter.id,name:chapter.name,level:'chapter',children:chapter.topics.map(topic => ({ id:topic.id,name:topic.name,level:'topic',children:topic.subtopics.map(node => ({ id:node.id,name:node.name,level:'subtopic',eligible:true,status:node.status,children:[] })) })) }));
}
