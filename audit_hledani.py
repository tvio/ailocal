"""Read-only rozklad skóre pro rozhodnutí o rozšíření dotazu a fulltextu.

Spuštění: .venv/Scripts/python.exe audit_hledani.py
Výstup: audit_hledani.json. Nemění data ani produkční hledání.
Používá pouze lokální embeddingy, žádný generativní model ani cloud.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from common.dotazy import rozsir
from common.hledani import Filtr, hledej, seskup
from common.ollama_client import embed
from evaluate import PARAFRAZE

DSN = "postgresql://readonly:readonly@localhost:5432/localsemantic"


def rank(rows, sem, fts, weight=0.8, threshold=0.60):
    # Stejná fúze jako aplikace, id navíc stabilizuje shody skóre.
    sr = {r['id']: i + 1 for i, r in enumerate(
        sorted(rows, key=lambda r: (-r[sem], r['id']))[:100])}
    fr = {r['id']: i + 1 for i, r in enumerate(
        sorted((r for r in rows if r[fts] > 0),
               key=lambda r: (-r[fts], r['id']))[:100])}
    out = []
    for r in rows:
        rid = r['id']
        if r[sem] < threshold or rid not in sr and rid not in fr:
            continue
        score = (weight / (60 + sr[rid]) if rid in sr else 0)
        score += ((1 - weight) / (60 + fr[rid]) if rid in fr else 0)
        out.append(dict(r, score=score))
    return sorted(out, key=lambda r: (-r['score'], r['id']))


def drugs(rows):
    seen = set()
    out = []
    for r in rows:
        if r['kod_sukl'] not in seen:
            seen.add(r['kod_sukl'])
            out.append(r)
    return out


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    queries = list(dict.fromkeys([q for q, _ in PARAFRAZE] + [
        'rýma', 'bolest hlavy', 'bolest zubů', 'zánět kůže',
        'kašel', 'kašlu', 'mám reflux', 'průjem u dětí',
        'nízký tlak', 'tlak v uchu', 'nemám rýmu']))
    variants = {q: rozsir(q) for q in queries}
    texts = list(dict.fromkeys(v for vs in variants.values() for v in vs))
    print(f'Embedding {len(texts)} formulací...', flush=True)
    vectors = dict(zip(texts, embed(texts)))
    result = {'created_utc': datetime.now(timezone.utc).isoformat(),
              'scope': 'indikace, bez routeru, práh 0.60; stabilní shody dle id',
              'queries': {}}
    with psycopg.connect(DSN, row_factory=dict_row) as conn:
        conn.execute('SET TRANSACTION READ ONLY')
        result['counts'] = conn.execute('''SELECT sekce,count(*) AS rows,
            count(klic) AS keys,count(embedding_klic) AS key_vectors
            FROM leciva_search GROUP BY sekce ORDER BY sekce''').fetchall()
        for q, vs in variants.items():
            columns = []
            par = {}
            for i, v in enumerate(vs):
                par[f'v{i}'] = str(vectors[v])
                par[f't{i}'] = v
                columns.extend([
                    f'1-(s.embedding <=> %(v{i})s::vector) AS t{i}',
                    f'COALESCE(1-(s.embedding_klic <=> %(v{i})s::vector),-1) AS k{i}',
                    f"s.search_fts @@ plainto_tsquery('czech_unaccent',%(t{i})s) AS match{i}",
                ])
            raw = conn.execute("SELECT replace(websearch_to_tsquery('czech_unaccent',%s)::text,'&','|') AS q", (q,)).fetchone()['q']
            stricts = [conn.execute("SELECT plainto_tsquery('czech_unaccent',%s)::text AS q", (v,)).fetchone()['q'] for v in vs]
            par['raw'] = raw
            par['strict'] = ' | '.join(f'({v})' for v in stricts if v)
            par['wide'] = par['strict'].replace('&', '|')
            for name in ('raw', 'strict', 'wide'):
                columns.append(f'ts_rank_cd(s.search_fts,%({name})s::tsquery) AS {name}')
            rows = conn.execute(f'''SELECT s.id,s.kod_sukl,l.nazev,s.klic,s.obsah_text,
                {', '.join(columns)} FROM leciva_search s JOIN leciva l USING(kod_sukl)
                WHERE s.sekce='indikace' AND s.embedding IS NOT NULL ORDER BY s.id''', par).fetchall()
            for r in rows:
                r['original_text'] = r['t0']
                r['original_both'] = max(r['t0'], r['k0'])
                r['expanded_text'] = max(r[f't{i}'] for i in range(len(vs)))
                r['current'] = max(r[f'{c}{i}'] for i in range(len(vs)) for c in ('t', 'k'))
                # Experiment: slovníková varianta přispěje jen s úplnou FTS shodou.
                # Původní dotaz zůstává sémantický i bez lexikální shody.
                r['gated'] = max([r['original_both']] + [
                    max(r[f't{i}'], r[f'k{i}']) for i in range(1, len(vs)) if r[f'match{i}']])
                winner = max(((r[f'{c}{i}'], i, c) for i in range(len(vs)) for c in ('t', 'k')))
                r['winner'] = {'query': vs[winner[1]], 'field': winner[2]}
            modes = {}
            for sem, ft in [('current', 'raw'), ('current', 'wide'),
                            ('current', 'strict'), ('gated', 'strict'),
                            ('original_both', 'raw')]:
                modes[f'{sem}/{ft}'] = [
                    {'id': r['id'], 'name': r['nazev'], 'cosine': r[sem],
                     'fts': r[ft], 'text': r['obsah_text']}
                    for r in drugs(rank(rows, sem, ft))[:10]]
            result['queries'][q] = {'variants': vs, 'tsqueries': {k: par[k] for k in ('raw', 'strict', 'wide')},
                'fts_hit_rows': {k: sum(r[k] > 0 for r in rows) for k in ('raw', 'strict', 'wide')},
                'modes': modes, 'rows': rows}
            print(q, '=>', [(r['name'], round(r['cosine'], 3)) for r in modes['current/raw'][:5]], flush=True)
    summary = {}
    for mode in next(iter(result['queries'].values()))['modes']:
        hits = [q for q, expected in PARAFRAZE if any(
            r['name'] in expected for r in result['queries'][q]['modes'][mode][:5])]
        summary[mode] = {'hit_at_5': len(hits), 'total': len(PARAFRAZE),
                         'misses': [q for q, _ in PARAFRAZE if q not in hits]}
    result['paraphrases'] = summary
    checks = []
    for q in ('mám rýmu', 'rýma'):
        for threshold in (0.0, 0.60):
            response = hledej(q, filtr=Filtr(sekce=['indikace']),
                             limit=60, prah=threshold, dsn=DSN)
            checks.append({'query': q, 'threshold': threshold, 'top5': [
                {'name': r.nazev, 'cosine': r.nejlepsi.cosine}
                for r in seskup(response.vysledky, leciv=5)]})
    result['production_checks_without_router'] = checks
    Path('audit_hledani.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
