"""
RUNNING TRAIN (走ル列車!) - joystick power/brake bridge. A prototype.

The game has no API like Train Sim World's, so the stick works the train through the game's own keys, as if you
pressed them:
    push forward  -> power notches (Z up, A down)
    centre        -> power N, brake released
    pull back     -> brake notches (. on, , off), never the emergency brake
The game doesn't say where its handles are, so the bridge counts the notches it has moved them. Each time the stick
comes back to centre it sends the handles to N and released with the game's own keys for that (Q and M), which work
from wherever the handles are, so a miscount is fixed there. (A key the game missed, or the keyboard used as well.)
After you start it, nothing is pressed until the stick moves.

Base slider -> reverser (+ end Forward, middle Neutral, - end Reverse): Down until it stops at Reverse, then Up
               to the one you picked, so it works whatever the reverser was at. Move it only when stopped.
Button 1 (trigger) -> ATS confirm (Space), held for as long as you hold the trigger
Button 2           -> horn (H), held for as long as you hold the button

Keys go to RUNNING TRAIN only: while another window is in front, nothing is pressed and any held key is let go.
The keys are read from the game's own save, so keys you changed in the game's settings are used. If the save can't
be read, the game's defaults are used (KEYS below).

Usage:
    python rt_joystick.py                run the bridge
    python rt_joystick.py --dry-run      print the keys it would press, without pressing them (no game needed)
    python rt_joystick.py --axes         show live joystick axis values
    python rt_joystick.py --notches 4 7  the train's power and brake notches (default 5 and 8)
"""

import ctypes
import os
import struct
import sys
import time

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", "1")  # read the stick while the game has focus
import pygame

# ---------------------------------------------------------------- settings
JOYSTICK_NAME_HINT = "extreme"   # prefers a device whose name contains this; else first joystick
Y_AXIS = 1                       # axis index for the stick's forward/back
INVERT_Y = False                 # set True if forward gives brake instead of power
DEADZONE = 0.08                  # around centre, treated as N / released
NOTCH_HYSTERESIS = 0.2           # past the halfway point by this fraction of a notch before moving to it

POWER_NOTCHES = 5                # P1-P5, as the ZUIKI one-handle MasCon the game supports
BRAKE_NOTCHES = 8                # B1-B8, emergency left out. If full back puts a train in emergency, lower this

USE_REVERSER = True
REVERSER_AXIS = 3                # Extreme 3D Pro base slider: + end Forward, middle Neutral, - end Reverse
REVERSER_INVERT = False
REVERSER_POSITIONS = 3           # Reverse, Neutral, Forward

ATS_BUTTON = 0                   # joystick button for ATS confirm (0 = trigger, labelled "1")
HORN_BUTTON = 1                  # labelled "2"

TAP_DOWN = 0.05                  # seconds each key is held down for one notch: longer than a game frame
TAP_GAP = 0.05                   # seconds between key presses
POLL_HZ = 60

# the game's keys, by the names in its save (Settings > Controls); used when the save can't be read
KEYS = {
    "power_up": "Z", "power_down": "A", "power_off": "Q",
    "brake_on": "Period", "brake_off": "Comma", "brake_release": "M",
    "reverser_forward": "Up", "reverser_back": "Down",
    "ats": "SpaceBar", "horn": "H",
}
SAVE_ACTIONS = {                 # the game's name for each action, in its save
    "ThrottleApply": "power_up", "ThrottleRelease": "power_down", "ThrottleNeutral": "power_off",
    "BrakeApply": "brake_on", "BrakeRelease": "brake_off", "BrakeNeutral": "brake_release",
    "ReverserUp": "reverser_forward", "ReverserDown": "reverser_back",
    "ATSConfirm": "ats", "Horn": "horn",
}
SAVE_FILE = os.path.join(os.environ.get("LOCALAPPDATA", ""), "RunningTrain", "Saved", "SaveGames", "CloudSave001.sav")
GAME_EXE = "runningtrain"        # RunningTrain-Win64-Shipping.exe


# ---------------------------------------------------------------- the game's keys
def save_strings(data):
    """Every length-prefixed ASCII string (Unreal FString) in a save, in file order."""
    out, i = [], 0
    while i < len(data) - 5:
        n = struct.unpack_from("<i", data, i)[0]
        if 1 <= n <= 300 and i + 4 + n <= len(data) and data[i + 4 + n - 1] == 0:
            s = data[i + 4:i + 4 + n - 1]
            if all(32 <= b < 127 for b in s):
                out.append(s.decode())
                i += 4 + n
                continue
        i += 1
    return out


def keys_from_save(data):
    """The game's key for each of our actions, read from its save's KB_SavedKeyBindings: {action: key name}.
    An action with no key in the game is left out."""
    strs = save_strings(data)
    if "KB_SavedKeyBindings" not in strs:
        return {}
    found, action = {}, None
    for j in range(strs.index("KB_SavedKeyBindings"), len(strs) - 2):
        s = strs[j]
        if s.startswith("Action_Name_") and strs[j + 1] == "NameProperty":
            action = strs[j + 2]
        elif s == "KeyName" and strs[j + 1] == "NameProperty" and action:
            key = strs[j + 2]
            if action in SAVE_ACTIONS and key != "None" and key in VK:
                found[SAVE_ACTIONS[action]] = key
            action = None
    return found


def load_keys(path=SAVE_FILE):
    """KEYS with the game's own keys from its save where they could be read. Returns (keys, note)."""
    keys = dict(KEYS)
    try:
        with open(path, "rb") as f:
            found = keys_from_save(f.read())
    except OSError as e:
        return keys, f"game's keys not read ({e.strerror}): using the defaults"
    if not found:
        return keys, "no keys found in the game's save: using the defaults"
    keys.update(found)
    for action in ("power_off", "brake_release"):       # no key for it in the game: count down instead
        if action not in found and action in KEYS:
            keys[action] = None
    return keys, f"keys read from the game's save ({len(found)} of {len(KEYS)})"


VK = {"SpaceBar": 0x20, "Period": 0xBE, "Comma": 0xBC, "Slash": 0xBF, "Semicolon": 0xBA, "Apostrophe": 0xDE,
      "LeftBracket": 0xDB, "RightBracket": 0xDD, "Hyphen": 0xBD, "Equals": 0xBB, "Backslash": 0xDC,
      "Enter": 0x0D, "Tab": 0x09, "BackSpace": 0x08,
      "Up": 0x26, "Down": 0x28, "Left": 0x25, "Right": 0x27,
      "Insert": 0x2D, "Delete": 0x2E, "Home": 0x24, "End": 0x23, "PageUp": 0x21, "PageDown": 0x22}
VK.update({chr(c): c for c in range(ord("A"), ord("Z") + 1)})
VK.update({name: 0x30 + i for i, name in enumerate(
    ["Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine"])})
VK.update({f"F{i}": 0x6F + i for i in range(1, 13)})
EXTENDED = {"Up", "Down", "Left", "Right", "Insert", "Delete", "Home", "End", "PageUp", "PageDown"}


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort), ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.c_size_t)]


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long), ("mouseData", ctypes.c_ulong),
                ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.c_size_t)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT)]   # the mouse one sets the size SendInput expects


class _INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("u", _INPUTUNION)]


def send_key(name, up=False):
    """A key going down (or up), as if pressed on the keyboard: its key code and scan code both."""
    vk = VK[name]
    scan = ctypes.windll.user32.MapVirtualKeyW(vk, 0)                  # MAPVK_VK_TO_VSC
    flags = (0x0002 if up else 0) | (0x0001 if name in EXTENDED else 0)  # KEYEVENTF_KEYUP, KEYEVENTF_EXTENDEDKEY
    inp = _INPUT(type=1, u=_INPUTUNION(ki=_KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=flags)))   # INPUT_KEYBOARD
    return ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT)) == 1


def game_has_focus():
    """True when the foreground window belongs to RUNNING TRAIN."""
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    pid = ctypes.c_ulong()
    user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), ctypes.byref(pid))
    handle = kernel32.OpenProcess(0x1000, False, pid.value)       # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return False
    try:
        buf = ctypes.create_unicode_buffer(520)
        size = ctypes.c_ulong(len(buf))
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return False
        return GAME_EXE in os.path.basename(buf.value).lower()
    finally:
        kernel32.CloseHandle(handle)


# ---------------------------------------------------------------- stick to notches
def shape_axis(raw, deadzone):
    """Apply a centre dead zone and rescale so the output still reaches +-1."""
    if abs(raw) < deadzone:
        return 0.0
    return (1.0 if raw > 0 else -1.0) * (abs(raw) - deadzone) / (1.0 - deadzone)


def notch_for(frac, notches, current=0):
    """The notch (0..notches) for frac (0..1) of the stick's travel. The notch it's in is kept until the stick is
    past halfway to the next by NOTCH_HYSTERESIS of a notch, so a stick held on a boundary doesn't flicker."""
    k = current
    while k < notches and frac > (k + 0.5 + NOTCH_HYSTERESIS) / notches:
        k += 1
    while k > 0 and frac < (k - 0.5 - NOTCH_HYSTERESIS) / notches:
        k -= 1
    return k


def reverser_zone(s, previous=None, hysteresis=0.06):
    """Slider value s (-1..+1, +1 = forward end) -> 1 forward / 0 neutral / -1 reverse.
    Hysteresis stops the choice flickering when the slider sits on a boundary."""
    edge = 1.0 / 3.0
    if previous == 1 and s > edge - hysteresis:
        return 1
    if previous == -1 and s < -edge + hysteresis:
        return -1
    if previous == 0 and -edge - hysteresis < s < edge + hysteresis:
        return 0
    return 1 if s > edge else -1 if s < -edge else 0


class Handles:
    """Where the bridge has put the game's power and brake handles, counted from the keys it pressed: the game
    doesn't say. None is not known: the first key then puts the handle at N / released from wherever it is."""

    def __init__(self, keys, power_notches=POWER_NOTCHES, brake_notches=BRAKE_NOTCHES):
        self.keys = keys
        self.power_notches, self.brake_notches = power_notches, brake_notches
        self.power = self.brake = None
        self._zero_power = self._zero_brake = False   # on the way down to N / released, a notch at a time

    def forget(self):
        """Count no longer trusted: the next keys put both handles at N / released."""
        self.power = self.brake = None
        self._zero_power = self._zero_brake = False

    def next_key(self, power, brake):
        """The next key to press on the way to power notch / brake notch, or None when they're there. Power is
        taken off before the brake goes on, and the brake released before power goes on."""
        if self.power is None:
            if self.keys["power_off"]:
                self.power = 0
                return self.keys["power_off"]
            # no key for N in the game: a notch down as many times as there are notches, so it's at N whatever
            self.power, self._zero_power = self.power_notches, True
        if self.brake is None:
            if self.keys["brake_release"]:
                self.brake = 0
                return self.keys["brake_release"]
            self.brake, self._zero_brake = self.brake_notches, True
        if power == 0 and self.power > 0 and self.keys["power_off"]:
            self.power = 0
            return self.keys["power_off"]
        if brake == 0 and self.brake > 0 and self.keys["brake_release"]:
            self.brake = 0
            return self.keys["brake_release"]
        if self.power > (0 if self._zero_power else power):
            self.power -= 1
            return self.keys["power_down"]
        self._zero_power = False
        if self.brake > (0 if self._zero_brake else brake):
            self.brake -= 1
            return self.keys["brake_off"]
        self._zero_brake = False
        if self.power < power:
            self.power += 1
            return self.keys["power_up"]
        if self.brake < brake:
            self.brake += 1
            return self.keys["brake_on"]
        return None

    def describe(self):
        if self.power is None or self.brake is None:
            return "not known yet"
        return f"P{self.power}" if self.power else f"B{self.brake}" if self.brake else "N"


class Reverser:
    """The reverser, worked from the base slider. The game doesn't say where it is, so each move goes Down until
    it stops at Reverse and then Up to the one picked."""

    def __init__(self, keys, positions=REVERSER_POSITIONS):
        self.keys, self.positions = keys, positions
        self.zone = None          # where the slider is: 1 forward / 0 neutral / -1 reverse
        self.pending = False      # moved since the keys were last pressed

    def update(self, s):
        zone = reverser_zone(s, self.zone)
        if self.zone is not None and zone != self.zone:
            self.pending = True
        self.zone = zone

    def take_keys(self):
        if not self.pending:
            return []
        self.pending = False
        ups = {-1: 0, 0: 1, 1: 2}[self.zone]
        return [self.keys["reverser_back"]] * (self.positions - 1) + [self.keys["reverser_forward"]] * ups


class Bridge:
    """Stick, slider and buttons in; keys out. Kept apart from the joystick and the keyboard so it can be tried
    without either."""

    def __init__(self, keys, power_notches=POWER_NOTCHES, brake_notches=BRAKE_NOTCHES):
        self.keys = keys
        self.power_notches, self.brake_notches = power_notches, brake_notches
        self.handles = Handles(keys, power_notches, brake_notches)
        self.reverser = Reverser(keys)
        self.want = (0, 0)        # power notch, brake notch the stick asks for
        self.centred = True       # stick in the dead zone
        self.moved = False        # the stick has left centre since the bridge started
        self.held = set()         # keys held down for joystick buttons
        self.buttons = {ATS_BUTTON: keys["ats"], HORN_BUTTON: keys["horn"]}

    def step(self, y, slider=None, buttons=(), focused=True):
        """What to do now, as [("tap" | "down" | "up", key)]. y: the stick after the dead zone, -1 (full brake)
        to +1 (full power); slider: the base slider -1..+1 (+1 forward), or None; buttons: joystick buttons held.
        At most one handle key a step, so the stick is read again between notches."""
        if y == 0:
            if not self.centred:
                self.handles.forget()       # back at centre: N and released with the game's own keys
            self.centred = True
            self.want = (0, 0)
        else:
            self.centred, self.moved = False, True
            power, brake = self.want
            self.want = ((notch_for(y, self.power_notches, power), 0) if y > 0
                         else (0, notch_for(-y, self.brake_notches, brake)))
        if slider is not None:
            self.reverser.update(slider)

        out = []
        if not focused:                     # never press keys into another window; let go of any held
            out += [("up", k) for k in sorted(self.held)]
            self.held.clear()
            return out
        for button, key in self.buttons.items():
            if button in buttons and key not in self.held:
                self.held.add(key)
                out.append(("down", key))
            elif button not in buttons and key in self.held:
                self.held.discard(key)
                out.append(("up", key))
        out += [("tap", k) for k in self.reverser.take_keys()]
        if self.moved:                      # nothing touched until the stick has moved
            key = self.handles.next_key(*self.want)
            if key:
                out.append(("tap", key))
        return out

    def describe(self):
        power, brake = self.want
        return f"P{power}" if power else f"B{brake}" if brake else "N"


# ---------------------------------------------------------------- running it
def open_joystick():
    pygame.joystick.quit()
    pygame.joystick.init()
    sticks = [pygame.joystick.Joystick(i) for i in range(pygame.joystick.get_count())]
    if not sticks:
        return None
    for s in sticks:
        if JOYSTICK_NAME_HINT in s.get_name().lower():
            return s
    return sticks[0]


def read_y(stick):
    raw = stick.get_axis(Y_AXIS) if Y_AXIS < stick.get_numaxes() else 0.0
    return shape_axis(raw if INVERT_Y else -raw, DEADZONE)     # joystick forward is negative; make it positive


def read_slider(stick):
    if not USE_REVERSER or REVERSER_AXIS >= stick.get_numaxes():
        return None
    raw = stick.get_axis(REVERSER_AXIS)
    return raw if REVERSER_INVERT else -raw


class Keyboard:
    """Presses keys with SendInput, or only prints them (dry run)."""

    def __init__(self, dry_run=False):
        self.dry_run = dry_run

    def do(self, what, key, note=""):
        if self.dry_run:
            print(f"\r{what:4s} {key:9s} {note}".ljust(78))
            if what == "tap":
                time.sleep(TAP_DOWN + TAP_GAP)
            return
        if what in ("tap", "down"):
            send_key(key)
        if what == "tap":
            time.sleep(TAP_DOWN)
        if what in ("tap", "up"):
            send_key(key, up=True)
        if what == "tap":
            time.sleep(TAP_GAP)


def show_axes():
    pygame.init()
    stick = open_joystick()
    if not stick:
        print("No joystick found.")
        return
    print(f"Joystick: {stick.get_name()}  ({stick.get_numaxes()} axes). Ctrl+C to stop.")
    while True:
        pygame.event.pump()
        vals = "  ".join(f"a{i}:{stick.get_axis(i):+.2f}" for i in range(stick.get_numaxes()))
        print("\r" + vals + f"   -> stick: {read_y(stick):+.2f}   ", end="", flush=True)
        time.sleep(0.05)


def run(dry_run=False, power_notches=POWER_NOTCHES, brake_notches=BRAKE_NOTCHES):
    keys, note = load_keys()
    print("RUNNING TRAIN joystick bridge" + (" - DRY RUN: keys are printed, not pressed" if dry_run else ""))
    print(f"  {note}")
    print("  power {power_up}/{power_down}, N {power_off}, brake {brake_on}/{brake_off}, released {brake_release}, "
          "reverser {reverser_forward}/{reverser_back}, ATS {ats}, horn {horn}".format(**keys))
    print(f"  stick: P1-P{power_notches} forward, B1-B{brake_notches} back. Ctrl+C to stop.\n")
    pygame.init()
    bridge = Bridge(keys, power_notches, brake_notches)
    keyboard = Keyboard(dry_run)
    stick, next_look = None, 0.0
    try:
        while True:
            for event in pygame.event.get():
                if event.type == pygame.JOYDEVICEREMOVED:
                    stick = None
            if stick is None:
                if time.time() >= next_look:
                    stick, next_look = open_joystick(), time.time() + 2.0
                    if stick:
                        print(f"\rJoystick: {stick.get_name()}".ljust(78))
                if stick is None:
                    print("\rWaiting for a joystick...".ljust(78), end="", flush=True)
                    time.sleep(0.2)
                    continue
            y = read_y(stick)
            buttons = {i for i in range(stick.get_numbuttons()) if stick.get_button(i)}
            focused = dry_run or game_has_focus()
            for what, key in bridge.step(y, read_slider(stick), buttons, focused):
                keyboard.do(what, key, f"(handles {bridge.handles.describe()}, stick asks {bridge.describe()})")
            where = "sending" if dry_run or focused else "RUNNING TRAIN not in front: waiting"
            print(f"\rStick {y:+.2f} -> {bridge.describe():3s} | handles {bridge.handles.describe():12s} | {where}"
                  .ljust(78), end="", flush=True)
            time.sleep(1.0 / POLL_HZ)
    except KeyboardInterrupt:
        pass
    finally:
        for key in sorted(bridge.held):
            keyboard.do("up", key)
        print("\nStopped.")


def main(argv):
    if "--axes" in argv:
        show_axes()
        return
    power, brake = POWER_NOTCHES, BRAKE_NOTCHES
    if "--notches" in argv:
        i = argv.index("--notches")
        power, brake = int(argv[i + 1]), int(argv[i + 2])
    run(dry_run="--dry-run" in argv, power_notches=power, brake_notches=brake)


if __name__ == "__main__":
    main(sys.argv[1:])
