# Rescued calibration records from the previous attempt

Recovered from `/var/lib/npec-camera/calibrations/arducam_64mp/` before that directory was
removed. Byte-identical copies. **These are the only surviving record of physically measured
values from the bench work of 2026-09-15/16.** They were outside version control.

Per the plan, these become **pre-filled config defaults that must be confirmed during
calibration** — fast setup, no silently inherited stale value.

## The measured values

| Quantity | Value | Note |
|---|---|---|
| **AprilTag size** | **29.3106 mm** | `tag_size_source: measured`. Nominal is 30 mm. |
| Tray height (stated) | 99.89 mm | As specified |
| Tray height (measured) | 116.21 mm | **Disagrees with stated by 16.3 mm — see below** |
| Camera distance to table | 1526.40 mm | ±1.93 mm |
| Table tilt | 2.76° | ±0.47° |
| Lens position | 6.3 dioptres | From EXIF |
| Sensor | 9152 × 6944 | Arducam 64MP, device serial `ae12ae4d29a8cc51` |
| Board | `A4_36H11_30MM_SHEET` | 28 board frames + 5 table frames |

Intrinsics and distortion coefficients are in the JSON. Per the plan's evidence gates, **we do not
use them** — they're kept as a record, not as an input.

## The 2.1% bias, and why it matters to the new design

The previous attempt recorded this defect honestly and never resolved it (`known_bias` field):

> *"Unattributed differential between the table's markers and the tray rim's: the table's behave as
> though 1.07% smaller, which is 2.1% in area and reads as +16 mm of tray height. It is a BIAS, not
> noise, so it is not in `pose.distance_sigma_mm` and does not shrink with more frames."*

That is the entire justification for the new architecture in one paragraph. The bias appears
**because two planes were being compared** — markers on the table versus markers on the tray rim.
It is not a lens problem, a noise problem, or a detector problem, which is why more frames and more
metrology never made it go away.

The new design measures **only in the tray-top focus plane**. Calibration sheets sit at tray
height, tray tags sit at tray height, plants sit at tray height. With one plane there is no
differential, and this bias has nothing to attach to.

The sigma values above are honest and worth keeping. The 16 mm tray-height discrepancy is the
artefact, not a real measurement of the trays.
