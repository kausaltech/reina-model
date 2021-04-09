import dataclasses
import typing
from dataclasses import dataclass
from enum import Enum

from flask_babel import lazy_gettext as _
from variables import get_variable
from calc.datasets import generate_mobility_ivs, generate_vaccination_ivs


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


VARIANTS = [(x['name'], x['name']) for x in get_variable('variants')]


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

    values: typing.Mapping[str, typing.Union[int, Choice, None]] = None
    date: str = None
    id: str = None

    def __post_init__(self):
        if self.parameters is None:
            self.parameters = []
        if self.values is None:
            self.values = {}

    def make_from_iv_tuple(self, iv):
        values = {}
        date = iv[1]
        iv = list(iv)[2:]
        for idx, p in enumerate(self.parameters):
            if not len(iv):
                break
            val = iv.pop(0)
            if val is None:
                continue
            if isinstance(p, IntParameter):
                assert val is None or isinstance(val, int)
            elif isinstance(p, ChoiceParameter):
                if val is not None:
                    assert isinstance(val, str)
                    for c in p.choices:
                        if val == c.id:
                            break
                    else:
                        raise Exception('Invalid choice value: %s' % val)
                    val = c
                else:
                    val = None

            values[p.id] = val

        obj = dataclasses.replace(self, values=values)
        obj.date = date
        return obj

    def get_param_values(self):
        out = {}
        if not self.values:
            return out
        for p in self.parameters:
            if isinstance(p, IntParameter):
                val = self.values.get(p.id)
            elif isinstance(p, ChoiceParameter):
                c = self.values.get(p.id)
                if not c:
                    continue
                val = c.id
            else:
                raise Exception('Invalid parameter type: %s' % type(p))
            out[p.id] = val
        return out

    def copy(self):
        obj = dataclasses.replace(self, values=dict(self.values))
        return obj

    def set_param(self, param_id, val):
        for p in self.parameters or []:
            if p.id == param_id:
                break
        else:
            raise Exception('Invalid parameter id: %s' % param_id)

        if isinstance(p, IntParameter):
            if val is not None and not isinstance(val, int):
                raise Exception('Requires int parameter: %s' % param_id)
            self.values[p.id] = val
        elif isinstance(p, ChoiceParameter):
            if val is not None:
                for c in p.choices:
                    if val == c.id:
                        break
                else:
                    raise Exception('Invalid choice value for %s: %s' % (param_id, val))
                val = c
            self.values[p.id] = val

    def make_iv_tuple(self):
        params = []
        for p in self.parameters:
            val = self.values.get(p.id)
            if isinstance(p, IntParameter):
                pass
            elif isinstance(p, ChoiceParameter):
                val = val.id if val else None
            params.append(val)
        return [self.type, self.date, *params]


INTERVENTIONS = [
    Intervention('test-all-with-symptoms', _('Test all patients with symptoms')),
    Intervention(
        'test-only-severe-symptoms',
        _('Test people only with severe symptoms'),
        parameters=[
            IntParameter(
                id='mild_detection_rate',
                label=_('Percentage of mild cases that are detected'),
                min_value=0,
                max_value=100,
                unit='%'
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
                min_value=0,
                max_value=100,
                unit='%',
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
                min_value=0,
                max_value=100,
                unit='%',
            ),
            IntParameter(
                id='min_age',
                label=_('Minimum age for limitation'),
                min_value=0,
                max_value=100,
                unit=_('years'),
                required=False,
            ),
            IntParameter(
                id='max_age',
                label=_('Maximum age for limitation'),
                min_value=0,
                max_value=100,
                unit=_('years'),
                required=False,
            ),
            ChoiceParameter(
                id='place',
                label=_('Place where the contacts happen'),
                choices=[Choice(x.name.lower(), x.label()) for x in ContactPlace],
                required=False,
            ),
        ],
    ),
    Intervention(
        'wear-masks',
        _('People wear masks'),
        parameters=[
            IntParameter(
                id='share_of_contacts',
                label=_('Portion of daily contacts where masks are in use'),
                min_value=0,
                max_value=100,
                unit='%',
            ),
            IntParameter(
                id='min_age',
                label=_('Minimum age for intervention'),
                min_value=0,
                max_value=100,
                unit=_('years'),
                required=False,
            ),
            IntParameter(
                id='max_age',
                label=_('Maximum age for intervention'),
                min_value=0,
                max_value=100,
                unit=_('years'),
                required=False,
            ),
            ChoiceParameter(
                id='place',
                label=_('Place where intervention happens'),
                choices=[Choice(x.name.lower(), x.label()) for x in ContactPlace],
                required=False,
            ),
        ],
    ),
    Intervention(
        'vaccinate',
        _('Vaccinate people against disease'),
        parameters=[
            IntParameter(
                id='weekly_vaccinations',
                label=_('Number of people vaccinated weekly'),
                min_value=0,
                unit=_('persons/week'),
            ),
            IntParameter(
                id='min_age',
                label=_('Minimum age for intervention'),
                min_value=0,
                max_value=100,
                unit=_('years'),
                required=False,
            ),
            IntParameter(
                id='max_age',
                label=_('Maximum age for intervention'),
                min_value=0,
                max_value=100,
                unit=_('years'),
                required=False,
            ),
        ],
    ),
    Intervention(
        'import-infections',
        _('Import infections from outside the area'),
        parameters=[
            IntParameter(id='amount', label=_('Amount of new infections'), unit=_('infections')),
            ChoiceParameter(
                id='variant',
                label=_('Variant of the disease'),
                choices=[Choice(x[0], x[1]) for x in VARIANTS],
                required=False,
            ),
        ]
    ),
    Intervention(
        'import-infections-weekly',
        _('Import infections from outside the area every week'),
        parameters=[
            IntParameter(id='weekly_amount', label=_('Amount of new weekly infections'), unit=_('infections/week')),
            *[IntParameter(
                id='variant_%s' % vid, label=_('Share of variant %(variant)s', variant=vlabel), unit=_('%'),
                required=False,
            ) for vid, vlabel in VARIANTS],
        ]
    ),
    Intervention(
        'build-new-hospital-beds',
        _('Build new hospital beds'),
        parameters=[
            IntParameter(id='beds', label=_('Number of new beds built'), unit=_('beds')),
        ],
    ),
    Intervention(
        'build-new-icu-units',
        _('Build new ICU units'),
        parameters=[
            IntParameter(id='units', label=_('Number of new ICU units built'), unit=_('ICU units')),
        ],
    ),
]
# Intervention('import-infections-per-day', _('Import new infections daily'), _('infections/day')),
# Intervention('limit-mass-gatherings', _('Limit mass gatherings'), _('max. contacts')),


def get_intervention(iv_type):
    for obj in INTERVENTIONS:
        if iv_type == obj.type:
            break
    else:
        raise Exception('Invalid intervention type: %s' % iv_type)
    return obj


def iv_tuple_to_obj(iv):
    obj = get_intervention(iv[0])
    return obj.make_from_iv_tuple(iv)


def get_active_interventions(variables=None):
    if variables:
        scenarios = variables['scenarios']
        active_scenario = variables['active_scenario']
        interventions = variables['interventions']
    else:
        scenarios = get_variable('scenarios')
        active_scenario = get_variable('active_scenario')
        interventions = get_variable('interventions')

    out = []
    for idx, iv in enumerate(interventions):
        obj = iv_tuple_to_obj(iv)
        obj.id = str(idx)
        out.append(obj)

    mobility_ivs = generate_mobility_ivs(variable_store=variables)
    for iv in mobility_ivs:
        out.append(iv_tuple_to_obj(iv))

    vaccinate_ivs = generate_vaccination_ivs(variable_store=variables)
    for iv in vaccinate_ivs:
        out.append(iv_tuple_to_obj(iv))

    if active_scenario:
        for s in scenarios:
            if s['id'] == active_scenario:
                break
        else:
            raise Exception('Invalid active scenario: %s' % active_scenario)
        added_ivs = s.get('add_interventions', [])
        for iv in added_ivs:
            out.append(iv_tuple_to_obj(iv))

    return out
