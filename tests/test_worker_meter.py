import importlib.util
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('meter', Path(__file__).parents[1]/
    '.agents/skills/web-workers/scripts/worker_meter.py')
meter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(meter)


class MeterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.now = 1000
        self.path = Path(self.tmp.name)/'ledger.sqlite'
        self.ledger = meter.Ledger(self.path, lambda: self.now)

    def tearDown(self):
        self.ledger.db.close()
        self.tmp.cleanup()

    def plan(self, **kw):
        return self.ledger.plan(dict(session='s', task='t', baseline=[800,1500],
            basis='test assumption', available_modes=['instant','high'], luna_available=True) | kw)

    def record(self, **kw):
        return self.ledger.record(dict(session='s', task='t', id='w', route='web',
            outcome='quota', seconds=1, overhead=[200,400], evidence='injected-test') | kw)

    def test_web_success_and_idempotent_record(self):
        self.assertEqual(self.plan()['model'], 'high')
        self.record(outcome='accepted')
        result = self.record(outcome='accepted')['tasks'][0]
        self.assertEqual(len(result['attempts']), 1)
        self.assertEqual(result['net_parent_tokens_estimate'], [400,1300])
        self.assertEqual(self.plan()['route'], 'done')
        with self.assertRaises(ValueError):
            self.record(outcome='rejected')

    def test_web_failure_luna_success_includes_both_costs(self):
        self.plan()
        self.record()
        self.assertEqual(self.plan()['route'], 'luna')
        result = self.record(id='l', route='luna', outcome='accepted', overhead=[300,600])
        self.assertEqual(result['tasks'][0]['net_parent_tokens_estimate'], [-200,1000])

    def test_both_fail_parent_has_negative_savings(self):
        self.plan()
        self.record()
        self.record(id='l', route='luna', outcome='unavailable', overhead=[300,600])
        self.assertEqual(self.plan()['route'], 'parent')
        result = self.record(id='p', route='parent', outcome='accepted', overhead=[0,0])
        self.assertEqual(result['tasks'][0]['net_parent_tokens_estimate'], [-1000,-500])

    def test_cooldown_survives_restart_expires_and_is_session_scoped(self):
        self.plan()
        self.record()
        self.ledger.db.close()
        self.ledger = meter.Ledger(self.path, lambda: self.now)
        self.assertEqual(self.plan(task='next')['route'], 'luna')
        self.assertEqual(self.plan(session='other')['route'], 'web')
        self.now += 3600
        self.assertEqual(self.plan(task='probe')['route'], 'web')
        self.assertEqual(self.plan()['route'], 'luna')

    def test_unresolved_blocks_until_confirmed_terminal(self):
        self.plan()
        self.record(outcome='unresolved')
        self.assertEqual(self.plan()['route'], 'wait')
        with self.assertRaises(ValueError):
            self.ledger.resolve(dict(session='s',task='t',id='w'))
        self.ledger.resolve(dict(session='s',task='t',id='w',terminal_confirmed=True))
        self.assertEqual(self.plan()['route'], 'luna')

    def test_unknown_never_zero_and_baseline_is_not_retroactive(self):
        self.plan(baseline=None)
        self.plan(baseline=[9000,10000])
        result = self.record(outcome='accepted')['tasks'][0]
        self.assertIsNone(result['net_parent_tokens_estimate'])

    def test_pending_and_unknown_overhead(self):
        self.plan()
        self.assertIsNone(self.record()['tasks'][0]['net_parent_tokens_estimate'])
        result = self.record(id='l',route='luna',outcome='accepted',overhead=None)
        self.assertIsNone(result['tasks'][0]['net_parent_tokens_estimate'])

    def test_usage_does_not_inflate_savings(self):
        self.plan()
        result = self.record(outcome='accepted', usage_tokens=100000)['tasks'][0]
        self.assertEqual(result['net_parent_tokens_estimate'], [400,1300])

    def test_running_reservation_prevents_duplicate_across_clients(self):
        self.plan()
        item = dict(session='s',task='t',id='w',route='web')
        self.ledger.start(item)
        other = meter.Ledger(self.path, lambda: self.now)
        try:
            with self.assertRaises(ValueError):
                other.start(item | {'id':'duplicate'})
            self.assertEqual(self.plan()['route'], 'wait')
        finally:
            other.db.close()
        self.record()
        self.assertEqual(self.plan()['route'], 'luna')

    def test_validation_and_no_fake_modes(self):
        for bad in [[-1,2],[4,2],[True,3],[float('nan'),5]]:
            with self.assertRaises(ValueError):
                self.plan(baseline=bad)
        self.assertEqual(self.plan(available_modes=['luna','made-up'])['route'], 'luna')
        self.assertEqual(self.plan(available_modes=[],luna_available=False)['route'], 'parent')

    def test_all_cooldowns_and_failed_probe_reopens(self):
        for outcome, duration in meter.COOLDOWNS.items():
            session = outcome
            self.plan(session=session)
            self.record(session=session,outcome=outcome)
            self.now += duration - 1
            self.assertEqual(self.plan(session=session,task='next')['route'], 'luna')
            self.now += 1
            self.assertEqual(self.plan(session=session,task='probe')['route'], 'web')
            self.record(session=session,task='probe',outcome=outcome)
            self.assertEqual(self.plan(session=session,task='later')['route'], 'luna')


if __name__ == '__main__':
    unittest.main()
