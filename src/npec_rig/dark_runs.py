"""Nights of an experiment (#419): the runs of lights-off photos the Gallery shows as one line.

Read from each photo's saved light mark (`exclusion.name`, exclusions.py); nothing is written.
"""

from datetime import datetime, timedelta

from npec_rig import database

LIGHTS_OFF = "lights off"
# Aaron's decision (2026-11-23), not a measurement: a shorter dark spell stays as photos.
SHORTEST_NIGHT = timedelta(minutes=15)


def night_runs(experiment_id: int) -> list[dict]:
    """The experiment's nights, oldest first: `start` and `end` (the first and last lights-off
    photo, UTC), `photos`, and `still_dark` (the newest photo is one of them).

    A run of lights-off photos counts as a night when both hold:
    - it lasts SHORTEST_NIGHT or more, from its first photo to the next lit one (for a night still
      going, to one photo interval after its newest photo);
    - it has a photo in the experiment's usual dark hours: the UTC hours in which more than half
      of its photos are lights off. A dark spell in the lit part of the day stays as photos.
    Raises LookupError for an unknown experiment."""
    experiment = database.get_experiment(experiment_id)
    photos = database.experiment_exclusions(experiment_id)
    interval = timedelta(seconds=experiment["interval_s"] or 0)
    # UTC ISO 8601: the hour is characters 11 and 12.
    hours = [int(p["taken_at"][11:13]) for p in photos]
    taken, dark = [0] * 24, [0] * 24
    for hour, photo in zip(hours, photos):
        taken[hour] += 1
        dark[hour] += photo["name"] == LIGHTS_OFF
    usually_dark = [2 * dark[h] > taken[h] for h in range(24)]

    nights: list[dict] = []
    i = 0
    while i < len(photos):
        if photos[i]["name"] != LIGHTS_OFF:
            i += 1
            continue
        first = i
        while i < len(photos) and photos[i]["name"] == LIGHTS_OFF:
            i += 1
        still_dark = i == len(photos)
        start = datetime.fromisoformat(photos[first]["taken_at"])
        if still_dark:
            ends = datetime.fromisoformat(photos[i - 1]["taken_at"]) + interval
        else:
            ends = datetime.fromisoformat(photos[i]["taken_at"])
        if ends - start >= SHORTEST_NIGHT and any(usually_dark[h] for h in hours[first:i]):
            nights.append({"start": photos[first]["taken_at"], "end": photos[i - 1]["taken_at"],
                           "photos": i - first, "still_dark": still_dark})
    return nights
