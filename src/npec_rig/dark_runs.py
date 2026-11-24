"""Dark runs of an experiment (#419): the runs of lights-off photos the Gallery shows as one line.

Read from each photo's saved light mark (`exclusion.name`, exclusions.py); nothing is written.
"""

from datetime import datetime, timedelta

from npec_rig import database

LIGHTS_OFF = "lights off"
# Aaron's decision (2026-11-23), not a measurement: a shorter dark spell stays as photos.
SHORTEST_NIGHT = timedelta(minutes=15)


def night_runs(experiment_id: int) -> list[dict]:
    """The experiment's dark runs, oldest first: `start` and `end` (the first and last lights-off
    photo, UTC), `photos`, and `still_dark` (the newest photo is one of them).

    Every run of consecutive lights-off photos that lasts SHORTEST_NIGHT or more counts, at any
    time of day (Aaron, 2026-11-24): from its first photo to the next lit one, or, for a run still
    going, to one photo interval after its newest photo. Raises LookupError for an unknown
    experiment."""
    experiment = database.get_experiment(experiment_id)
    photos = database.experiment_exclusions(experiment_id)
    interval = timedelta(seconds=experiment["interval_s"] or 0)
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
        if ends - start >= SHORTEST_NIGHT:
            nights.append({"start": photos[first]["taken_at"], "end": photos[i - 1]["taken_at"],
                           "photos": i - first, "still_dark": still_dark})
    return nights
