"""Rebuildable provenance graph and lexical/optional local semantic search."""
from __future__ import annotations
import collections
import math
import re
from pathlib import Path
from .common import PMError, relpath, safe_json
from .knowledge import iter_docs, load_doc, links, load_config, authority_of, infer_status

ARCHIVED_STATUSES = {'archived', 'superseded', 'historical'}


# Latin words plus CJK overlapping bigrams. This is lexical, NOT model-based semantics.
def terms(text: str) -> list[str]:
    text = text.lower()
    latin = re.findall(r'[a-z0-9_]+', text)
    cjk_runs = re.findall(r'[\u3400-\u9fff]+', text)
    return latin + [run[i:i + 2] for run in cjk_runs for i in range(max(1, len(run) - 1))]


def issue_snapshots(repo: Path):
    for folder, prefix in [('issues', 'ISSUE'), ('prs', 'PR')]:
        for p in sorted((repo / '.project-memory' / folder).glob('*.json')):
            obj = safe_json(p)
            if not isinstance(obj, dict) or not isinstance(obj.get('number'), int):
                continue
            yield prefix, obj, relpath(repo, p)


def visible(node: dict, include_archived: bool = False, include_mirror: bool = False) -> bool:
    if node.get('type') in ('issue', 'pull_request'):
        return True
    authority = node.get('authority', 'canonical')
    if authority == 'legacy':
        return include_archived
    if authority == 'mirror' and not include_mirror:
        return False
    if not include_archived and node.get('status') in ARCHIVED_STATUSES:
        return False
    return True


def build_graph(repo: Path, config: dict | None = None) -> dict:
    cfg = config or load_config(repo)
    nodes: dict[str, dict] = {}
    edges: set[tuple[str, str, str]] = set()
    for path in iter_docs(repo, cfg['doc_roots'] + cfg['mirror_roots'] + cfg['legacy_roots']):
        meta, text = load_doc(path)
        loc = relpath(repo, path)
        authority = authority_of(loc, cfg)
        is_adr = loc.startswith(cfg['adr_dir'].rstrip('/') + '/') and meta.get('kind') == 'adr'
        ident = str(meta.get('id') or loc)
        node_id = ident if is_adr else 'DOC:' + loc
        nodes[node_id] = {
            'id': node_id,
            'type': 'adr' if is_adr else 'document',
            'path': loc,
            'title': str(meta.get('title') or path.stem),
            'status': infer_status(meta, loc, authority),
            'authority': authority,
            'text': text[:50000],
        }
        arefs, irefs, drefs = links(text)
        arefs.update(v for v in meta.get('related_adrs', []) if isinstance(v, str))
        irefs.update(v for v in meta.get('related_issues', []) if isinstance(v, int))
        for adr in arefs:
            if adr != node_id:
                edges.add((node_id, adr, 'references'))
        for num in irefs:
            edges.add((node_id, f'ISSUE:{num}', 'references'))
        for p in drefs:
            if p != loc:
                edges.add((node_id, 'DOC:' + p, 'references'))
        for pred in meta.get('supersedes', []):
            edges.add((node_id, str(pred), 'supersedes'))
    for prefix, obj, path in issue_snapshots(repo):
        num = obj['number']
        node_id = f'{prefix}:{num}'
        content = (str(obj.get('title') or '') + '\n' + str(obj.get('body') or ''))[:50000]
        nodes[node_id] = {'id': node_id, 'type': 'issue' if prefix == 'ISSUE' else 'pull_request', 'path': path, 'title': obj.get('title') or f'{prefix} #{num}', 'status': obj.get('state') or 'unknown', 'authority': 'canonical', 'text': content}
        ars, irs, docs = links(content)
        for adr in ars:
            edges.add((node_id, adr, 'references'))
        for ref in irs:
            if ref != num:
                edges.add((node_id, f'ISSUE:{ref}', 'references'))
        for p in docs:
            edges.add((node_id, 'DOC:' + p, 'references'))
    unresolved = []
    for src, dst, kind in edges:
        if dst not in nodes:
            unresolved.append({'from': src, 'to': dst, 'relation': kind})
    return {'schema_version': '1.1', 'kind': 'knowledge_graph', 'nodes': list(nodes.values()), 'edges': [{'from': a, 'to': b, 'relation': c} for a, b, c in sorted(edges)], 'unresolved': sorted(unresolved, key=lambda x: (x['from'], x['to']))}


def lexical_search(graph: dict, query: str, top_k: int = 6, include_archived: bool = False, include_mirror: bool = False) -> list[dict]:
    nodes = [n for n in graph['nodes'] if visible(n, include_archived, include_mirror)]
    q = collections.Counter(terms(query))
    if not q:
        return []
    docs = [collections.Counter(terms(n['title'] + ' ' + n['text'])) for n in nodes]
    df = collections.Counter(t for d in docs for t in d)
    N = max(1, len(docs))
    scored = []
    for n, tf in zip(nodes, docs):
        score = 0.0
        for term, count in q.items():
            if term in tf:
                score += min(3, count) * math.log1p(tf[term]) * (1 + math.log((N + 1) / (df[term] + 1)))
        if score > 0:
            text = n['text'].replace('\n', ' ')
            pos = next((text.lower().find(t) for t in q if text.lower().find(t) >= 0), 0)
            scored.append({
                'id': n['id'],
                'type': n['type'],
                'path': n['path'],
                'title': n['title'],
                'authority': n.get('authority', 'canonical'),
                'status': n.get('status', 'unknown'),
                'score': round(score, 5),
                'excerpt': text[max(0, pos - 75):pos + 235],
            })
    scored.sort(key=lambda x: (-x['score'], x['id']))
    return scored[:top_k]


def semantic_search(graph: dict, query: str, model_path: str, top_k: int = 6, include_archived: bool = False, include_mirror: bool = False) -> list[dict]:
    """True embedding search, opt-in and *local model only*; no download. No cache in MVP."""
    path = Path(model_path).expanduser().resolve()
    if not path.is_dir():
        raise PMError('--model 必须指向已存在的本地 sentence-transformers 模型目录；不允许使用远程标识')
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        raise PMError('语义检索需要额外的 sentence-transformers；请在受控环境中安装后再用') from None
    try:
        model = SentenceTransformer(str(path), local_files_only=True)
        nodes = [n for n in graph['nodes'] if visible(n, include_archived, include_mirror)]
        if not nodes:
            return []
        chunks = []
        for idx, n in enumerate(nodes):
            content = n['title'] + '\n' + n['text']
            for offset in range(0, min(len(content), 12000), 1000):
                chunks.append((idx, content[offset:offset + 1200]))
        vecs = model.encode([query] + [x[1] for x in chunks], normalize_embeddings=True)
        scores = {}
        for (idx, chunk), vec in zip(chunks, vecs[1:]):
            s = float(sum(float(a) * float(b) for a, b in zip(vecs[0], vec)))
            if idx not in scores or s > scores[idx][0]:
                scores[idx] = (s, chunk)
        result = []
        for idx, (s, chunk) in scores.items():
            n = nodes[idx]
            result.append({
                'id': n['id'],
                'type': n['type'],
                'path': n['path'],
                'title': n['title'],
                'authority': n.get('authority', 'canonical'),
                'status': n.get('status', 'unknown'),
                'score': round(s, 5),
                'excerpt': chunk[:300],
            })
        return sorted(result, key=lambda x: (-x['score'], x['id']))[:top_k]
    except (OSError, ValueError, RuntimeError) as e:
        raise PMError(f'本地嵌入模型运行失败：{type(e).__name__}: {e}') from None
