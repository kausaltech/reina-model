from dataclasses import dataclass

from flask_babel import lazy_gettext as _
from .mobility import MOBILITY_PLACES


@dataclass
class Metric:
    id: str
    label: str
    description: str = None
    unit: str = None
    color: str = None
    is_integer: bool = False
    is_simulated: bool = True
    is_categorized: bool = False


METRICS = [
    Metric(
        'susceptible',
        _('Susceptible'),
        None,
        _('residents'),
        color='yellow',
        is_integer=True,
    ),
    Metric(
        'vaccinated',
        _('Vaccinated'),
        None,
        _('residents'),
        color='#78C091',
        is_integer=True,
        is_categorized=True,
    ),
    Metric(
        'infected',
        _('Active infections'),
        None,
        _('residents'),
        'purple',
        is_integer=True,
    ),
    Metric(
        'all_infected',
        _('Total infections (cum.)'),
        None,
        _('residents'),
        None,
        is_integer=True,
    ),
    Metric(
        'new_infections',
        _('New daily infections (14 day avg.)'),
        None,
        _('infections'),
        'purple',
        is_integer=True,
    ),
    Metric(
        'detected',
        _('Detected cases (14 day avg.)'),
        None,
        _('cases'),
        'teal',
        is_integer=True,
    ),
    Metric(
        'all_detected',
        _('Detected cases'),
        None,
        _('cases (cum.)'),
        'teal',
        is_integer=True,
    ),
    Metric(
        'in_ward',
        _('In hospital ward'),
        None,
        _('beds in use'),
        'orange',
        is_integer=True,
    ),
    Metric(
        'in_icu',
        _('In ICU'),
        None,
        _('ICU units in use'),
        'red',
        is_integer=True,
    ),
    Metric(
        'dead',
        _('Dead'),
        None,
        _('deaths (cum.)'),
        'indigo',
        is_integer=True,
    ),
    Metric(
        'recovered',
        _('Recovered'),
        None,
        _('residents'),
        '#84b082',
        is_integer=True,
    ),
    #
    # Healthcare capacity
    #
    Metric(
        'available_hospital_beds',
        _('Available hospital beds'),
        None,
        _('beds'),
        is_integer=True,
    ),
    Metric(
        'available_icu_units',
        _('Available ICU units'),
        None,
        _('ICU units'),
        is_integer=True,
    ),
    Metric(
        'r',
        _('Reproductive number (Rₜ)'),
        description=None,
        unit=None,
        color=None,
        is_integer=False,
    ),
    Metric(
        'ifr',
        _('Infection fatality ratio (IFR)'),
        description=None,
        unit='%',
        color=None,
        is_integer=False,
    ),
    Metric(
        'cfr',
        _('Case fatality ratio (CFR)'),
        description=None,
        unit='%',
        color=None,
        is_integer=False,
    ),
    # Metric(
    #     'infected_by_variant',
    #     _('New infections by variant type'),
    #     description=None,
    #     unit=_('infections'),
    #     color=None,
    #     is_integer=True,
    #     is_categorized=True,
    # ),
]

MOBILITY_METRICS = [
    Metric(
        '%s_mobility_change' % p_id,
        p['name'],
        description=_('Change in mobility compared to baseline'),
        unit='%',
        is_integer=True,
    ) for p_id, p in MOBILITY_PLACES.items()
]

ALL_METRICS = METRICS + MOBILITY_METRICS


def get_metric(metric_id):
    for m in ALL_METRICS:
        if m.id == metric_id:
            return m
    else:
        return None
