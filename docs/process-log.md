# Process log

How the work went, round by round: Aaron's decisions, the agents' work and errors, and what slowed
the round. 5 to 10 lines per round, added at each round review (PLAN.md, *Records kept for every
round*). The measurements themselves are in `docs/metrology-log.md`.

## Round 1 (15 to 22 October 2026)

Written at the round 1 review, 2026-10-19 (`docs/metrology-log.md`, 15.6).

- 2026-10-14 to 10-16: on the academic supervisor's advice, the work is planned in CRISP-DM rounds
  of about 2 weeks with fixed end dates. The rounds set the order of work; milestones M3 to M6 stay
  as pools of issues. Only the next round is planned in detail. Final target: canopy area within
  5% per tray (95% band) at tray-top height; plant height is a stretch goal.
- 2026-10-16: tray splitting and green-threshold plant area moved into round 1, before scheduled
  capture, so plant and segmentation problems show up first. Round 1 is scripts on saved stills;
  from round 2 every round ends with something in the web app.
- 2026-10-16: every board card gets a Round field, and every result in the metrology log is
  labelled a development check, a validation or a reference comparison (`GLOSSARY.md`).
- Agent error: an early CRISP-DM draft was written before it was asked for, and the agreed plan
  had two rosette diameters swapped (SW and SE). Both were caught and corrected on 2026-10-16.
- What slowed the round: two issues stayed open for days because each held the round review,
  which cannot be written before the round's last photo session. On 2026-10-17 the review got
  its own issue (#217), and from round 2 each round's review issue is opened when the round starts.
- 2026-10-19, at the review: FastSAM tray splitting dropped after it failed on touching trays with
  pots (53% to 56% right). Trays are placed from a tag in cell A1, in any rotation, using the slot
  grid for which way the tray faces (288 of 288 checked by Aaron, 15.5k). Round 2 tray tag: about
  40 mm, in A1. Placement target: no tray in a wrong slot without a warning, at least 95% placed.
  No separate white balance study. The round 2 run mixes still hours with shuffles to printed maps.
- Agents' work: round 1 ran as scripts on 358 saved stills (176 empty trays, 182 with pots) plus
  the benchmark and leaf sessions, every method written in the log before its analysis.
- Agent errors: the 15.5c count took 7 tray positions 52 to 225 mm off as right (its slot rule
  could not see them; caught by the tracking in 15.5d). The first cell-tag rule took the tray's
  direction from the tag heading, so one tag lying 180 degrees round put its tray in the wrong slot
  in every still with no warning (15.5i); fixed in 15.5j after Aaron pointed out that operators
  will not follow a rule on tag orientation.
- What slowed the round: four days on FastSAM splitting and its patches before pots showed it
  failing on touching trays; the method that worked (tag placement) needed no Hailo and was found
  in one afternoon.
