"""Physical qualification decisions; fixtures do not establish hardware proof."""
import unittest
from workbench.watch_controls import matches, restoration, channels, gesture_decision
from workbench.watch_disconnect import recovery_checks

def sample():
    return {'buttons': 0, 'controller_read': 1, 'sticks': dict(lx=130, ly=129, rx=132, ry=126),
            'front': {'read_result': 0, 'contacts': []}, 'rear': {'read_result': 0, 'contacts': []}}

class Decisions(unittest.TestCase):
    def test_each_stick_and_wrong_side(self):
        s = sample(); s['sticks']['lx'] = 240
        self.assertTrue(matches('left-stick', s)); self.assertFalse(matches('right-stick', s))
        s['sticks']['rx'] = 240
        self.assertFalse(matches('left-stick', s))
    def test_button_exact_and_mixed(self):
        s = sample(); s['buttons'] = 128
        self.assertTrue(matches('buttons', s))
        s['buttons'] |= 16
        self.assertFalse(matches('buttons', s))
        s['buttons'] = 128; s['rear']['contacts'] = [{'x': .5, 'y': .5}]
        self.assertFalse(matches('buttons', s))
    def test_front_panel_and_safe_area(self):
        s = sample(); s['front']['contacts'] = [{'x': .5, 'y': .96}]
        self.assertTrue(matches('front-touch', s)); self.assertFalse(matches('rear-touch', s))
        s['front']['contacts'][0]['y'] = .914
        self.assertTrue(matches('front-touch', s))
        s['front']['contacts'][0]['y'] = .6
        self.assertFalse(matches('front-touch', s))
    def test_rear_panel_separate(self):
        s = sample(); s['rear']['contacts'] = [{'x': .5, 'y': .5}]
        self.assertTrue(matches('rear-touch', s)); self.assertFalse(matches('front-touch', s))
    def test_invalid_input_read_is_not_neutral(self):
        s = sample(); s['controller_read'] = -1
        with self.assertRaises(RuntimeError): channels(s)
        s = sample(); s['front']['read_result'] = -1
        with self.assertRaises(RuntimeError): channels(s)
    def test_motion_or_mixed_activity_does_not_pass(self):
        p = dict(motion_fresh=True, lease_remaining_ms=20000, dimmed=False, idle_elapsed_ms=40, last_activity_flags=1, brightness=34389)
        self.assertTrue(restoration('buttons', p, 34389))
        for changes in ({'last_activity_flags': 9}, {'last_activity_flags': 3}, {'lease_remaining_ms': 0}, {'motion_fresh': False}, {'idle_elapsed_ms': 2000}, {'brightness': 6877}, {'dimmed': True}):
            self.assertFalse(restoration('buttons', {**p, **changes}, 34389))

    def test_staggered_power_and_input_snapshots_wait_for_pair(self):
        p = dict(motion_fresh=True, lease_remaining_ms=20000, dimmed=False, idle_elapsed_ms=40, last_activity_flags=2, brightness=34389)
        s = sample()
        self.assertEqual(gesture_decision('left-stick', s, p, 34389), 'await paired sample')
        s['sticks']['lx'] = 240
        self.assertEqual(gesture_decision('left-stick', s, p, 34389), 'passed')
        s['sticks']['rx'] = 240
        self.assertEqual(gesture_decision('left-stick', s, p, 34389), 'confounded')
        s = sample(); s['sticks']['lx'] = 240
        self.assertEqual(gesture_decision('left-stick', s, {**p, 'last_activity_flags': 10}, 34389), 'confounded')

    def test_wifi_expiry_or_activity_cannot_count_as_network_proof(self):
        b = dict(brightness=34389, idle_elapsed_ms=5000)
        a = dict(brightness=34389, idle_elapsed_ms=10000, lease_remaining_ms=0, dimmed=False)
        self.assertTrue(all(recovery_checks('wifi', b, a, 8, 5, 5).values()))
        self.assertFalse(all(recovery_checks('wifi', b, a, -2, 35, 5).values()))
        self.assertFalse(all(recovery_checks('wifi', b, {**a, 'idle_elapsed_ms': 200}, 8, 5, 5).values()))
        self.assertFalse(all(recovery_checks('wifi', b, {**a, 'brightness': 6877}, 8, 5, 5).values()))
        self.assertFalse(all(recovery_checks('wifi', b, a, 8, .2, 5).values()))
        # A gesture followed by a longer wait cannot pass solely because the
        # final inactivity age exceeds the earlier five-second baseline.
        self.assertFalse(all(recovery_checks('wifi', b, a, 8, 15, 15).values()))

    def test_sleep_recovery_requires_work_end_and_restored_brightness(self):
        b = dict(brightness=34389, idle_elapsed_ms=5000)
        a = dict(brightness=34389, idle_elapsed_ms=100, lease_remaining_ms=0, dimmed=False)
        self.assertTrue(all(recovery_checks('sleep', b, a, -20, 50).values()))
        self.assertFalse(all(recovery_checks('sleep', b, {**a, 'lease_remaining_ms': 2000}, -20, 50).values()))

    def test_native_touch_panel_metadata_must_match_gesture(self):
        p = dict(motion_fresh=True, lease_remaining_ms=20000, dimmed=False, idle_elapsed_ms=40,
                 last_activity_flags=4, brightness=34389, touch_read_result=0, physical_touch_panels=1, touch_source_pid=77)
        self.assertTrue(restoration('front-touch', p, 34389))
        self.assertFalse(restoration('rear-touch', p, 34389))
        for changes in ({'physical_touch_panels': 3}, {'touch_read_result': -1}, {'touch_source_pid': 0}):
            self.assertFalse(restoration('front-touch', {**p, **changes}, 34389))

    def test_clock_independent_touch_diagnostics_require_fresh_foreground_reader(self):
        panel = dict(reader_pid=77, native_contacts=1, source_ticks=900000000000, advances=50, changed_ms=1000)
        p = dict(motion_fresh=True, lease_remaining_ms=20000, dimmed=False, idle_elapsed_ms=40,
                 last_activity_flags=4, brightness=34389, touch_read_result=0, physical_touch_panels=1,
                 touch_source_pid=77, touch_sample_ms=1100, touch_diagnostics=[panel, {}])
        self.assertTrue(restoration('front-touch', p, 34389))
        for changes in ({'reader_pid': 88}, {'native_contacts': 0}, {'source_ticks': 0}, {'advances': 0}, {'changed_ms': 500}, {'changed_ms': 1101}):
            self.assertFalse(restoration('front-touch', {**p, 'touch_diagnostics': [{**panel, **changes}, {}]}, 34389))

if __name__ == '__main__': unittest.main(verbosity=2)
