import dataclasses
import typing
from dataclasses import dataclass
from enum import Enum

from flask_babel import lazy_gettext as _


class ContactPlace(Enum):
    HOME = 1
    WORK = 2
    SCHOOL = 3
    TRANSPORT = 4
    LEISURE = 5
    OTHER = 6

    def label(self):
        TRANSLATIONS = {
            self.HOME: _('Home'),
            self.WORK: _('Work'),
            self.SCHOOL: _('School'),
            self.TRANSPORT: _('Transport'),
            self.LEISURE: _('Leisure'),
            self.OTHER: _('Other'),
        }
        return TRANSLATIONS[self]


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

    def copy_from_iv_tuple(self, iv):
        params = []
        for idx, p in enumerate(self.parameters or []):
            if len(iv) <= 2 + idx:
                break
            o = dataclasses.replace(p)  # creates a copy
            if isinstance(p, IntParameter):
                o.value = iv[2 + idx]
            elif isinstance(p, ChoiceParameter):
                value = iv[2 + idx]
                for c in p.choices:
                    if value == c.id:
                        break
                else:
                    raise Exception('Invalid choice value')
                o.choice = c
            params.append(o)

        obj = dataclasses.replace(self, parameters=params)
        obj.date = iv[1]
        return obj


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
                choices=[Choice(x.name.lower(), x.label()) for x in ContactPlace],
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


def iv_tuple_to_obj(iv):
    for obj in INTERVENTIONS:
        if iv[0] == obj.type:
            break
    else:
        raise Exception()

    return obj.copy_from_iv_tuple(iv)
