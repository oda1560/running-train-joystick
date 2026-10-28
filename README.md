# RUNNING TRAIN joystick bridge (prototype)

Drive RUNNING TRAIN (走ル列車!) with a flight stick, laid out like the TSW joystick bridge: push forward for power, pull back to brake, centre for N with the brake released. Built for the Logitech Extreme 3D Pro.

The game has no API, so the bridge presses the game's own keys for you. It reads which keys those are from the game's save, so keys you change in the game's settings are followed.

## Starting it

Double-click **Start Running Train Joystick.bat**, then click into the game. Keys only go to RUNNING TRAIN: while another window is in front, nothing is pressed.

You need Python 3 with pygame, the same as the TSW bridge.

| Command | What it does |
| --- | --- |
| `python rt_joystick.py` | Runs the bridge |
| `python rt_joystick.py --dry-run` | Prints the keys it would press instead of pressing them. No game needed |
| `python rt_joystick.py --notches 4 7` | For a train with P1–P4 and B1–B7 (the default is 5 and 8) |
| `python rt_joystick.py --axes` | Shows the stick's raw axis values |

## Controls

| Joystick | Keys it presses | What it does |
| --- | --- | --- |
| Stick forward | `Z` / `A` | Power, a notch per key, up to P5 at full travel |
| Stick centre | `Q` and `M` | Power to N and brake released, from wherever the handles are |
| Stick back | `.` / `,` | Brake, up to B8 at full travel. Never the emergency brake |
| Base slider | `Down` then `Up` | Reverser: + end Forward, middle Neutral, − end Reverse. Move it only when stopped |
| Trigger | `Space` | ATS confirm, held while you hold the trigger |
| Button 2 | `H` | Horn, held while you hold the button |

Nothing is pressed until you move the stick, so the keyboard still works on its own.

## How it keeps track

The game doesn't say where its handles are, so the bridge counts the notches it has moved them. When you bring the stick back to centre it presses `Q` and `M`. Those keys put the handles at N and released from anywhere, so a wrong count is fixed each time you centre the stick: a key the game missed, or a notch you moved from the keyboard.

Power comes off before the brake goes on, and the brake is released before power goes on.

## Check on the first drive

These couldn't be tried without driving the game:

- **One key, one notch.** The bridge holds each key down for 50 ms with 50 ms between keys (`TAP_DOWN`, `TAP_GAP`). If the game misses notches, make both longer.
- **Number of notches.** Full forward should give the train's top power notch, and full back its top service brake. If a train has fewer, start with `--notches`.
- **No emergency at full back.** If pressing `.` past the last service notch puts a train into emergency, lower the brake notches for that train.
- **Reverser direction.** `Up` is taken as towards Forward.

Settings are at the top of `rt_joystick.py`. Tests (no game, joystick or keyboard needed):

```bash
python -m unittest discover tests
```
