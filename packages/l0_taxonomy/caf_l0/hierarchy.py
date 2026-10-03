"""Version-scoped traversal shared by serving, classification and intelligence."""

from collections import defaultdict

import sqlalchemy as sa
from sqlalchemy.orm import Session

from caf_db.models.ref import Node


def node_scope(session: Session):
    """Draft nodes never leak into the currently serving hierarchy."""
    from caf_db.models.taxonomy import TaxonomyMember, TaxonomyRelease
    from caf_l0.releases import active_version

    release = active_version(session)
    if release:
        return Node.id.in_(sa.select(TaxonomyMember.node_id).where(
            TaxonomyMember.taxonomy_version_id == release.taxonomy_version_id
        ))
    return Node.id.not_in(sa.select(TaxonomyMember.node_id).join(
        TaxonomyRelease,
        TaxonomyRelease.taxonomy_version_id == TaxonomyMember.taxonomy_version_id,
    ).where(TaxonomyRelease.status != "legacy"))


def version_nodes(session: Session, taxonomy_version_id: int | None = None) -> list[Node]:
    from caf_db.models.taxonomy import TaxonomyMember

    query = sa.select(Node).order_by(Node.seq, Node.id)
    if taxonomy_version_id is None:
        query = query.where(node_scope(session))
    else:
        query = query.where(Node.id.in_(sa.select(TaxonomyMember.node_id).where(
            TaxonomyMember.taxonomy_version_id == taxonomy_version_id
        )))
    return list(session.scalars(query))


def leaf_scope(session: Session):
    """Classification counts include each terminal subtopic once."""
    from sqlalchemy.orm import aliased

    child = aliased(Node)
    return sa.and_(Node.level == "subtopic", Node.status == "active", node_scope(session),
        ~sa.exists(sa.select(child.id).where(child.parent_id == Node.id)))


def ancestors(node_id: str, nodes: dict[str, Node]) -> list[Node]:
    chain = []
    seen = set()
    current = nodes.get(node_id)
    while current:
        if current.id in seen:
            raise ValueError(f"Taxonomy ancestry cycle at {current.id}")
        seen.add(current.id)
        chain.append(current)
        current = nodes.get(current.parent_id) if current.parent_id else None
    return list(reversed(chain))


def ancestor_at(node_id: str, nodes: dict[str, Node], level: str) -> Node | None:
    return next((node for node in reversed(ancestors(node_id, nodes)) if node.level == level), None)


def descendant_leaves(node_id: str, nodes: dict[str, Node]) -> list[str]:
    children = defaultdict(list)
    for node in nodes.values():
        if node.parent_id:
            children[node.parent_id].append(node.id)
    pending = [node_id]
    visited = set()
    leaves = set()
    while pending:
        current_id = pending.pop()
        if current_id in visited:
            raise ValueError(f"Taxonomy cycle or duplicate ancestry at {current_id}")
        visited.add(current_id)
        current = nodes.get(current_id)
        if current is None:
            continue
        if current.level == "subtopic" and not children[current_id]:
            leaves.add(current_id)
        else:
            pending.extend(children[current_id])
    return sorted(leaves)
