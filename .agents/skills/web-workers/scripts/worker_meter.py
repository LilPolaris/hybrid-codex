"""Local routing ledger. JSON on stdin; no prompts, credentials or network calls.

python -X utf8 worker_meter.py --db <private.sqlite> <plan|record|summary>
Token ranges are scenario estimates of incremental Parent work, not billing usage.
"""
import argparse
import json
import math
import os
from pathlib import Path
import sqlite3
import time

MODES = ['pro', 'extra-high', 'high', 'medium', 'instant']
COOLDOWNS = {'auth': 1800, 'quota': 3600, 'unavailable': 600,
             'transient': 60}
OUTCOMES = {'accepted', 'rejected', 'auth', 'quota', 'unavailable', 'transient',
            'cancelled', 'unresolved'}


def interval(value):
    if (not isinstance(value, list) or len(value) != 2 or
            any(isinstance(x, bool) or not isinstance(x, (int, float)) or
                not math.isfinite(x) or x < 0 for x in value) or value[0] > value[1]):
        raise ValueError('Expected a nonnegative ordered [low, high] token range')
    return value


class Ledger:
    def __init__(self, path, now=time.time):
        self.now = now
        self.db = sqlite3.connect(path, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS tasks (
          session TEXT, task TEXT, baseline TEXT, basis TEXT,
          PRIMARY KEY(session,task));
        CREATE TABLE IF NOT EXISTS attempts (
          session TEXT, task TEXT, id TEXT, route TEXT, outcome TEXT,
          seconds REAL, overhead TEXT, usage INTEGER, model TEXT, evidence TEXT,
          created REAL, PRIMARY KEY(session,task,id));
        CREATE TABLE IF NOT EXISTS cooldown (
          session TEXT, route TEXT, reason TEXT, until REAL,
          PRIMARY KEY(session,route));
        ''')

    def plan(self, data):
        session, task = data['session'], data['task']
        baseline = interval(data['baseline']) if data.get('baseline') is not None else None
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO tasks VALUES(?,?,?,?)',
                            (session, task, json.dumps(baseline), data.get('basis', 'unknown')))
        attempts = self.db.execute('SELECT * FROM attempts WHERE session=? AND task=?',
                                   (session, task)).fetchall()
        if any(a['outcome'] in {'unresolved', 'running'} for a in attempts):
            return {'route': 'wait', 'reason': 'owned job unresolved; confirm termination first'}
        if any(a['outcome'] == 'accepted' for a in attempts):
            return {'route': 'done', 'reason': 'verified result already accepted'}
        failed = {a['route'] for a in attempts}
        blocked = {r['route']: dict(r) for r in self.db.execute(
            'SELECT * FROM cooldown WHERE session=? AND until>?', (session, self.now()))}
        available = data.get('available_modes', [])
        mode = next((m for m in MODES if m in available), None)
        if mode and 'web' not in failed and 'web' not in blocked:
            route, model = 'web', mode
        elif data.get('luna_available', False) and 'luna' not in failed and 'luna' not in blocked:
            route, model = 'luna', 'gpt-5.6-luna/max'
        else:
            route, model = 'parent', 'current native Parent'
        return {'route': route, 'model': model, 'cooldowns': list(blocked.values()),
                'previous_routes': sorted(failed)}

    def start(self, data):
        # Serializes launch reservation across Parent processes using this ledger.
        self.db.execute('BEGIN IMMEDIATE')
        try:
            if self.db.execute("SELECT 1 FROM attempts WHERE session=? AND task=? "
                               "AND outcome IN ('running','unresolved','accepted')",
                               (data['session'], data['task'])).fetchone():
                raise ValueError('Subtask already running, unresolved or complete')
            if data['route'] not in {'web', 'luna', 'parent'}:
                raise ValueError('Invalid route')
            if not self.db.execute('SELECT 1 FROM tasks WHERE session=? AND task=?',
                                   (data['session'], data['task'])).fetchone():
                raise ValueError('Plan first')
            self.db.execute('INSERT INTO attempts VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                (data['session'], data['task'], data['id'], data['route'], 'running', 0,
                 'null', None, data.get('model','unverified'), data.get('evidence','live'), self.now()))
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return {'reserved': data['id'], 'route': data['route']}

    def record(self, data):
        session, task, ident = data['session'], data['task'], data['id']
        route, outcome = data['route'], data['outcome']
        if route not in {'web', 'luna', 'parent'} or outcome not in OUTCOMES:
            raise ValueError('Unknown route/outcome')
        overhead = interval(data['overhead']) if data.get('overhead') is not None else None
        seconds = data['seconds']
        if not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or seconds < 0:
            raise ValueError('Invalid elapsed seconds')
        usage = data.get('usage_tokens')
        if usage is not None and (type(usage) is not int or usage < 0):
            raise ValueError('usage_tokens must be measured integer or null')
        if not self.db.execute('SELECT 1 FROM tasks WHERE session=? AND task=?',
                               (session, task)).fetchone():
            raise ValueError('Plan before recording; estimate baseline before delegation')
        values = (session, task, ident, route, outcome, seconds, json.dumps(overhead), usage,
                  data.get('model', 'unverified'), data.get('evidence', 'live'), self.now())
        with self.db:
            old = self.db.execute('SELECT * FROM attempts WHERE session=? AND task=? AND id=?',
                                  (session, task, ident)).fetchone()
            if old:
                if old['outcome'] == 'running' and old['route'] == route:
                    self.db.execute('UPDATE attempts SET outcome=?, seconds=?, overhead=?, usage=?, '
                                    'model=?, evidence=? WHERE session=? AND task=? AND id=?',
                                    (outcome,seconds,json.dumps(overhead),usage,values[8],values[9],session,task,ident))
                elif tuple(old)[:-1] != values[:-1]:
                    raise ValueError('Attempt id already exists with different data')
            else:
                self.db.execute('INSERT INTO attempts VALUES(?,?,?,?,?,?,?,?,?,?,?)', values)
            if not old or old['outcome'] == 'running':
                if outcome in COOLDOWNS:
                    self.db.execute('INSERT INTO cooldown VALUES(?,?,?,?) ON CONFLICT(session,route) '
                                    'DO UPDATE SET reason=excluded.reason, until=MAX(until,excluded.until)',
                                    (session, route, outcome, self.now() + COOLDOWNS[outcome]))
                elif outcome == 'accepted':
                    self.db.execute('DELETE FROM cooldown WHERE session=? AND route=?', (session, route))
        return self.summary({'session': session, 'task': task})

    def resolve(self, data):
        if data.get('terminal_confirmed') is not True:
            raise ValueError('Confirm terminal state from the owned job handle first')
        with self.db:
            self.db.execute("UPDATE attempts SET outcome='cancelled' WHERE session=? AND task=? "
                            "AND id=? AND outcome IN ('unresolved','running')",
                            (data['session'], data['task'], data['id']))
        return self.summary(data)

    def summary(self, data):
        results = []
        for task in self.db.execute('SELECT * FROM tasks WHERE session=? ORDER BY task', (data['session'],)):
            if data.get('task') and data['task'] != task['task']:
                continue
            rows = [dict(r) for r in self.db.execute(
                'SELECT * FROM attempts WHERE session=? AND task=? ORDER BY created,id',
                (data['session'], task['task']))]
            base = json.loads(task['baseline'])
            costs = [json.loads(r['overhead']) for r in rows]
            accepted = any(r['outcome'] == 'accepted' and r['route'] != 'parent' for r in rows)
            finished = any(r['outcome'] == 'accepted' for r in rows)
            # Rejected work earns no benefit; all Parent delegation overhead still counts.
            net = None
            if rows and finished and base is not None and all(c is not None for c in costs):
                benefit = base if accepted else [0, 0]
                net = [round(benefit[0] - sum(c[1] for c in costs)),
                       round(benefit[1] - sum(c[0] for c in costs))]
            seconds = round(sum(r['seconds'] for r in rows), 1)
            routes = ' → '.join(r['route'] + '/' + r['model'] for r in rows) or 'pending'
            estimate = f'{net[0]:+,}…{net[1]:+,}' if net is not None else '待估算'
            card = f"委派 {task['task']} | {routes} | {seconds}s | 主模型净节省估算 {estimate} tokens"
            results.append({'task': task['task'], 'basis': task['basis'], 'baseline': base,
                            'net_parent_tokens_estimate': net, 'adopted': accepted,
                            'finished': finished, 'attempts': rows, 'card': card})
        return {'tasks': results, 'notice': '情景估算，非实际账单或额度；不含不可见推理、缓存和上下文重放。'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['plan', 'start', 'record', 'resolve', 'summary'])
    default = Path(os.environ.get('CODEX_HOME') or Path.home()/'.codex')/'worker-metrics'/'ledger.sqlite'
    parser.add_argument('--db', type=Path, default=default)
    args = parser.parse_args()
    args.db.parent.mkdir(parents=True, exist_ok=True)
    data = json.load(__import__('sys').stdin)
    ledger = Ledger(args.db)
    try:
        print(json.dumps(getattr(ledger, args.action)(data), ensure_ascii=False, indent=2))
    finally:
        ledger.db.close()


if __name__ == '__main__':
    main()
