from dataclasses import dataclass

from flask_babel import lazy_gettext as _


@dataclass
class Metric:
    id: str
    label: str
    description: str = None
    unit: str = None
    color: str = None
    is_integer: bool = False
    is_simulated: bool = True


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
        'all_detected',
        _('Detected cases'),
        None,
        _('cases (cum.)'),
        'teal',
        is_integer=True,
    ),
    Metric(
        'hospitalized',
        _('Hospitalized'),
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
        'green',
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
]

VALIDATION_METRICS = [
    #
    # Real observed metrics
    #
    Metric(
        'confirmed_real',
        _('Detected cases (real)'),
        description=None,
        unit=_('cases (cum.)'),
        color='teal',
        is_integer=True,
        is_simulated=False,
    ),
    Metric(
        'hospitalized_real',
        _('Hospitalized (real)'),
        description=None,
        unit=_('beds in use'),
        color='orange',
        is_integer=True,
        is_simulated=False,
    ),
    Metric(
        'in_icu_real',
        _('In ICU (real)'),
        description=None,
        unit=_('ICU units in use'),
        color='red',
        is_integer=True,
        is_simulated=False,
    ),
    Metric(
        'dead_real',
        _('Dead (real)'),
        description=None,
        unit=_('deaths (cum.)'),
        color='indigo',
        is_integer=True,
        is_simulated=False,
    ),
]

ALL_METRICS = METRICS + VALIDATION_METRICS


def get_metric(metric_id):
    for m in ALL_METRICS:
        if m.id == metric_id:
            return m
    else:
        return None
