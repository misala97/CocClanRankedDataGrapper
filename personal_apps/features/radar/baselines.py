# personal_apps/features/radar/baselines.py
"""How loud a ticker normally is, per source.

The estimator divides observed counts by the observed MASS of the buckets it
used -- their combined share of a normal week -- rather than by how many
buckets there were. That single choice is what makes every gap rule in the
design safe rather than merely survivable: dropping a bucket removes its share
from the denominator as well as its count from the numerator, so the rate is
unchanged no matter which buckets went or how busy they usually are.

Dividing by bucket count would be fooled by exactly the case that matters. Lose
the US session to an outage and a count-based divisor reports the ticker as
having gone quiet.
"""
import dataclasses
import datetime as dt

from .profile import hour_share


@dataclasses.dataclass
class Observation:
    """One bucket of one ticker on one source."""
    bucket_start: dt.datetime
    count: int
    status: str
    config_version: str


def usable(observations, config_version, excluded):
    """The buckets a baseline may be built from.

    Three exclusions, all for one reason -- each describes something other than
    this ticker being normally quiet or normally loud:

    - `missing` is a source that was down, `truncated` a known undercount
      (spec 4.5)
    - a different `source_config_version` measured a different population
      (spec 6.6)
    - `excluded` is the caller's own set, wired to open spikes in Plan 3, so a
      ticker that squeezed last week does not carry the squeeze into its own
      baseline
    """
    return [o for o in observations
            if o.status == 'ok'
            and o.config_version == config_version
            and o.bucket_start not in excluded]


def weekly_rate(observations, prof, prior_rate=None, prior_weight=0.0):
    """Mentions per week, and the mass of week actually observed.

    `prior_weight` is in the same units as mass -- 0.05 is worth about eight
    hours of observation, so it dominates on day one and disappears once there
    is real history (spec 6.8).
    """
    if not observations:
        return 0.0, 0.0

    observed_mass = sum(hour_share(prof, o.bucket_start) for o in observations)
    total = sum(o.count for o in observations)

    if observed_mass <= 0:
        return 0.0, 0.0

    if prior_rate is None or prior_weight <= 0:
        return total / observed_mass, observed_mass

    # Shrink towards the prior in mass units, so the weight of the evidence
    # decides, not the number of rows it arrived in.
    blended = (total + prior_rate * prior_weight) / (observed_mass + prior_weight)
    return blended, observed_mass
