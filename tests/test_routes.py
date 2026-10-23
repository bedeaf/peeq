import json
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class RoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.home = tempfile.TemporaryDirectory()
        home = Path(cls.home.name)
        (home / '.config/speaker-eq').mkdir(parents=True)
        profile = json.loads((ROOT / 'profiles/t14.json').read_text())
        (home / '.config/speaker-eq/profile.json').write_text(json.dumps(profile))
        with patch.object(Path, 'home', return_value=home):
            cls.controller = runpy.run_path(str(ROOT / 'bin/speaker-eq'), run_name='test_subject')
        cls.profile = profile

    @classmethod
    def tearDownClass(cls):
        cls.home.cleanup()

    def master(self, availability='not available', active='speaker'):
        return {'name': self.profile['master'], 'active_port': active, 'ports': [
            {'name': 'speaker', 'type': 'speaker', 'availability': 'available'},
            {'name': 'headphones', 'type': 'headphones', 'availability': availability},
        ]}

    def route(self, sinks, default=None, enabled=True):
        return self.controller['choose_route'](
            sinks, default or self.profile['eq_sink'], enabled)

    def test_speakers_use_eq(self):
        self.assertEqual(self.route([self.master()]),
                         (self.profile['eq_sink'], 'speaker', 'speaker'))

    def test_disabled_eq_uses_direct_speakers(self):
        self.assertEqual(self.route([self.master()], enabled=False),
                         (self.profile['master'], 'speaker', 'bypass'))

    def test_jack_availability_overrides_stale_active_port(self):
        self.assertEqual(self.route([self.master('available')]),
                         (self.profile['master'], 'headphones', 'headphones'))

    def test_unknown_jack_uses_active_headphone_port(self):
        self.assertEqual(self.route([self.master('availability unknown', 'headphones')])[2],
                         'headphones')

    def test_disconnected_jack_does_not_keep_stale_headphone_port(self):
        self.assertEqual(self.route([self.master('not available', 'headphones')])[2], 'speaker')

    def test_selected_external_output_is_respected(self):
        for name in ['usb-output', 'bluetooth-output', 'hdmi-output']:
            with self.subTest(name=name):
                external = {'name': name, 'active_port': 'output', 'ports': [
                    {'name': 'output', 'availability': 'available'}]}
                self.assertEqual(self.route([self.master(), external], name),
                                 (name, None, 'external'))

    def test_unavailable_external_output_falls_back(self):
        external = {'name': 'hdmi', 'active_port': 'output', 'ports': [
            {'name': 'output', 'availability': 'not available'}]}
        self.assertEqual(self.route([self.master(), external], 'hdmi')[2], 'speaker')

    def test_missing_card_skips_filters_and_prefers_headset(self):
        sinks = [
            {'name': self.profile['eq_sink']},
            {'name': 'other-filter', 'properties': {'device.class': 'filter'}},
            {'name': 'usb-speakers', 'properties': {}},
            {'name': 'usb-headset', 'properties': {'device.form_factor': 'headset'}},
        ]
        self.assertEqual(self.route(sinks), ('usb-headset', None, 'external'))

    def test_no_hardware_output_is_unavailable(self):
        self.assertEqual(self.route([{'name': self.profile['eq_sink']}]),
                         (None, None, 'unavailable'))

    def test_unknown_port_types_do_not_get_speaker_eq(self):
        master = {'name': self.profile['master'], 'ports': []}
        self.assertEqual(self.route([master]), (self.profile['master'], None, 'bypass'))

    def test_module_order_matches_signal_path_and_control_arrays(self):
        args = self.controller['module_args']()
        for arg, sink, master, key in zip(args,
                ['limiter_sink', 'tone_sink', 'eq_sink'],
                ['master', 'limiter_sink', 'tone_sink'],
                ['limiter_controls', 'eq_controls', 'preamp_controls']):
            self.assertIn('sink_name=' + self.profile[sink], arg)
            self.assertIn('master=' + self.profile[master], arg)
            self.assertIn('control=' + ','.join(map(str, self.profile[key])), arg)
            self.assertIn('rate=48000 channels=2', arg)


if __name__ == '__main__':
    unittest.main()
