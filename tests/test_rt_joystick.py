"""
Tests for rt_joystick.py: which keys the stick presses, without the game, a joystick or a keyboard.

    python -m unittest discover tests
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import rt_joystick as rt  # noqa: E402

SAVE = os.path.join(os.environ.get("LOCALAPPDATA", ""), "RunningTrain", "Saved", "SaveGames", "CloudSave001.sav")


def taps(bridge, y, steps=40, **kw):
    """Keys tapped while the stick is held at y for a number of steps."""
    out = []
    for _ in range(steps):
        out += [k for what, k in bridge.step(y, **kw) if what == "tap"]
    return out


class Notches(unittest.TestCase):
    def test_full_stick_is_the_top_notch(self):
        self.assertEqual(rt.notch_for(1.0, 5), 5)
        self.assertEqual(rt.notch_for(1.0, 8), 8)

    def test_a_notch_is_kept_near_its_boundary(self):
        k = rt.notch_for(0.5, 4)                 # P2, half way
        self.assertEqual(k, 2)
        self.assertEqual(rt.notch_for(0.40, 4, k), 2)   # just under 2.0 notches' worth: still P2
        self.assertEqual(rt.notch_for(0.30, 4, k), 1)   # well under: P1

    def test_reverser_zones(self):
        self.assertEqual(rt.reverser_zone(1.0), 1)
        self.assertEqual(rt.reverser_zone(0.0), 0)
        self.assertEqual(rt.reverser_zone(-1.0), -1)
        self.assertEqual(rt.reverser_zone(0.30, previous=1), 1)       # hysteresis


class Driving(unittest.TestCase):
    def setUp(self):
        self.b = rt.Bridge(dict(rt.KEYS), power_notches=5, brake_notches=8)

    def test_nothing_is_pressed_until_the_stick_moves(self):
        self.assertEqual(taps(self.b, 0.0), [])

    def test_first_push_puts_handles_at_n_then_notches_up(self):
        self.assertEqual(taps(self.b, 1.0), ["Q", "M", "Z", "Z", "Z", "Z", "Z"])

    def test_back_to_centre_uses_the_n_and_released_keys(self):
        taps(self.b, 0.6)
        self.assertEqual(taps(self.b, 0.0), ["Q", "M"])
        self.assertEqual(taps(self.b, 0.0), [])                       # only once

    def test_easing_off_power_notches_down(self):
        taps(self.b, 1.0)
        self.assertEqual(taps(self.b, 0.5), ["A", "A"])              # P5 -> P3

    def test_brake_goes_on_only_after_power_is_off(self):
        taps(self.b, 0.6)
        out = taps(self.b, -0.5)
        self.assertEqual(out[0], "Q")
        self.assertEqual(out[1:], ["Period"] * 4)                     # B4 of 8 at half travel

    def test_power_goes_on_only_after_the_brake_is_released(self):
        taps(self.b, -1.0)
        self.assertEqual(taps(self.b, 0.4), ["M", "Z", "Z"])          # P2 of 5

    def test_full_back_is_full_service_never_emergency(self):
        out = taps(self.b, -1.0, steps=100)
        self.assertEqual(out.count("Period"), 8)
        self.assertNotIn("Slash", out)

    def test_without_an_n_key_power_counts_down_from_the_top(self):
        keys = dict(rt.KEYS, power_off=None)
        b = rt.Bridge(keys, power_notches=4, brake_notches=7)
        self.assertEqual(taps(b, 0.2), ["M", "A", "A", "A", "A", "Z"])   # all the way down, then up to P1

    def test_no_keys_while_the_game_is_not_in_front(self):
        self.assertEqual(taps(self.b, 1.0, focused=False), [])
        self.assertEqual(taps(self.b, 1.0)[:2], ["Q", "M"])        # in front again: carries on

    def test_buttons_are_held_and_let_go_when_the_game_loses_focus(self):
        self.assertEqual(self.b.step(0.0, buttons={rt.ATS_BUTTON}), [("down", "SpaceBar")])
        self.assertEqual(self.b.step(0.0, buttons={rt.ATS_BUTTON}), [])
        self.assertEqual(self.b.step(0.0, buttons={rt.ATS_BUTTON}, focused=False), [("up", "SpaceBar")])

    def test_reverser_goes_to_reverse_then_up_to_the_one_picked(self):
        self.assertEqual(taps(self.b, 0.0, steps=1, slider=0.0), [])  # first reading: nothing
        self.assertEqual(taps(self.b, 0.0, steps=1, slider=1.0), ["Down", "Down", "Up", "Up"])
        self.assertEqual(taps(self.b, 0.0, steps=1, slider=-1.0), ["Down", "Down"])
        self.assertEqual(taps(self.b, 0.0, steps=1, slider=-1.0), [])


class GameKeys(unittest.TestCase):
    def test_keys_from_a_save(self):
        def fstr(s):
            b = s.encode() + b"\0"
            return len(b).to_bytes(4, "little") + b
        data = b"GVAS" + b"".join(fstr(s) for s in [
            "KB_SavedKeyBindings", "ArrayProperty",
            "Action_Name_30_X", "NameProperty", "ThrottleApply", "KeyName", "NameProperty", "X",
            "Action_Name_30_X", "NameProperty", "BrakeNeutral", "KeyName", "NameProperty", "None",
            "Action_Name_30_X", "NameProperty", "Wiper", "KeyName", "NameProperty", "K"])
        self.assertEqual(rt.keys_from_save(data), {"power_up": "X"})

    @unittest.skipUnless(os.path.exists(SAVE), "RUNNING TRAIN's save isn't on this PC")
    def test_this_pcs_save(self):
        keys, note = rt.load_keys(SAVE)
        self.assertIn("read from the game's save", note)
        for action, key in keys.items():
            self.assertTrue(key is None or key in rt.VK, (action, key))


if __name__ == "__main__":
    unittest.main()
