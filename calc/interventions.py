import typing
from dataclasses import dataclass

from flask_babel import lazy_gettext as _


@dataclass
class Parameter:
    id: str
    label: str
    required: bool = True


@dataclass
class IntParameter(Parameter):
    min_value: int = None
    max_value: int = None
    unit: str = None


@dataclass
class Choice:
    id: str
    label: str


@dataclass
class ChoiceParameter(Parameter):
    choices: typing.List[Choice] = None


@dataclass
class Intervention:
    type: str
    label: str
    parameters: typing.List[Parameter] = None


INTERVENTIONS = [
    Intervention(
        'test-all-with-symptoms', _('Test all patients with symptoms')
    ),
    Intervention(
        'test-only-severe-symptoms',
        _('Test people only with severe symptoms'),
        parameters=[
            IntParameter(
                id='efficiency',
                label=_('Percentage of mild cases that are detected'),
                min_value=0, max_value=100, unit='%'
            ),
        ]
    ),
    Intervention(
        'test-with-contact-tracing',
        _('Test all with symptoms and perform contact tracing'),
        parameters=[
            IntParameter(
                id='efficiency',
                label=_('Percentage of infectors that are caught through contact tracing'),
                min_value=0, max_value=100, unit='%',
            ),
        ]
    ),
    Intervention(
        'limit-mobility',
        _('Limit population mobility'),
        parameters=[
            IntParameter(
                id='reduction',
                label=_('Reduction in contacts'),
                min_value=0, max_value=100, unit='%',
            ),
            IntParameter(
                id='min_age',
                label=_('Minimum age for limitation'),
                min_value=0, max_value=100, unit=_('years'),
                required=False,
            ),
            IntParameter(
                id='max_age',
                label=_('Maximum age for limitation'),
                min_value=0, max_value=100, unit=_('years'),
                required=False,
            ),
            ChoiceParameter(
                id='place', label=_('Place where the contacts happen'),
                choices=[
                    Choice('home', _('Home'))
                ],
                required=False,
            ),
        ],
    ),
    Intervention(
        'import-infections',
        _('Import infections from outside the area'),
        parameters=[
            IntParameter(
                id='amount',
                label=_('Amount of new infections'),
                unit=_('infections')
            ),
        ]
    ),
    # Intervention('build-new-hospital-beds', _('Build new hospital beds'), _('beds')),
    # Intervention('build-new-icu-units', _('Build new ICU units'), _('units')),
]
