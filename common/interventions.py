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
    value: int = None


@dataclass
class Choice:
    id: str
    label: str


@dataclass
class ChoiceParameter(Parameter):
    choices: typing.List[Choice] = None
    choice: Choice = None


@dataclass
class Intervention:
    type: str
    label: str
    parameters: typing.List[Parameter] = None

    def make_from_iv_tuple(self, iv):
        params = []
        date = iv[1]
        iv = list(iv)[2:]
        for idx, p in enumerate(self.parameters or []):
            if not len(iv):
                break
            val = iv.pop(0)
            if val is None:
                continue
            o = dataclasses.replace(p)  # creates a copy
            if isinstance(p, IntParameter):
                assert val is None or isinstance(val, int)
                o.value = val
            elif isinstance(p, ChoiceParameter):
                if val is not None:
                    assert isinstance(val, str)
                    for c in p.choices:
                        if val == c.id:
                            break
                    else:
                        raise Exception('Invalid choice value: %s' % val)
                    o.choice = c
                else:
                    o.choice = None
            params.append(o)

        obj = dataclasses.replace(self, parameters=params)
        obj.date = date
        return obj

    def get_param_values(self):
        out = {}
        for p in (self.parameters or []):
            if isinstance(p, IntParameter):
                if not p.value:
                    continue
                val = p.value
            elif isinstance(p, ChoiceParameter):
                if not p.choice:
                    continue
                val = p.choice.id
            else:
                raise Exception('Invalid parameter type: %s' % type(p))
            out[p.id] = val
        return out


INTERVENTIONS = [
    Intervention(
        'test-all-with-symptoms', _('Test all patients with symptoms')
    ),
    Intervention(
        'test-only-severe-symptoms',
        _('Test people only with severe symptoms'),
        parameters=[
            IntParameter(
                id='mild_detection_rate',
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
    Intervention(
        'build-new-hospital-beds',
        _('Build new hospital beds'),
        parameters=[
            IntParameter(
                id='beds',
                label=_('Number of new beds built'),
                unit=_('beds')
            ),
        ],
    ),
    Intervention(
        'build-new-icu-units',
        _('Build new ICU units'),
        parameters=[
            IntParameter(
                id='units',
                label=_('Number of new ICU units built'),
                unit=_('ICU units')
            ),
        ],
    ),
]
# Intervention('import-infections-per-day', _('Import new infections daily'), _('infections/day')),
# Intervention('limit-mass-gatherings', _('Limit mass gatherings'), _('max. contacts')),


def iv_tuple_to_obj(iv):
    for obj in INTERVENTIONS:
        if iv[0] == obj.type:
            break
    else:
        raise Exception('Invalid intervention type: %s' % iv[0])

    return obj.make_from_iv_tuple(iv)
