from collections import Counter
from time import perf_counter
import sqlalchemy as sa
from caf_db.engine import get_engine, get_session_factory
from caf_api.auth import Principal
from caf_api.routes import list_papers, get_paper_tree, get_subtopic_detail, get_dashboard
from caf_l5.context import resolve_context, context_nodes

engine = get_engine('student')
queries = Counter()
@sa.event.listens_for(engine, 'before_cursor_execute')
def before(conn, cursor, statement, parameters, context, executemany):
    queries[statement.split('\n')[0][:140]] += 1
account = Principal(1, 'Profile', None, 'administrator', 'active')
with get_session_factory('student')() as s:
    s.execute(sa.text('SET TRANSACTION READ ONLY'))
    context = resolve_context(s, 1)
    nodes = context_nodes(s, context, study=True)
    paper_id = nodes[0].paper_id
    leaf = next(n.id for n in nodes if n.level == 'subtopic')
    s.rollback()
for name, call in [('context', lambda s: resolve_context(s,1)),('papers',lambda s:list_papers(s,account)),('tree',lambda s:get_paper_tree(paper_id,s,account)),('subtopic',lambda s:get_subtopic_detail(leaf,s,account)),('dashboard',lambda s:get_dashboard(s,account))]:
    for iteration in range(2):
        with get_session_factory('student')() as s:
            s.execute(sa.text('SET TRANSACTION READ ONLY'))
            s.info["cache_study_context"] = True; queries.clear()
            start=perf_counter()
            result=call(s)
            print(name,iteration,round(perf_counter()-start,3),'seconds',sum(queries.values()),'queries',flush=True)
            if iteration==1:
                print('top repeats',queries.most_common(5),flush=True)
            s.rollback()
