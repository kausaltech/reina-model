from typing import Dict
from dataclasses import dataclass
from flask_babel import get_locale, lazy_gettext as _


DEFAULT_LOCALE = 'en'


@dataclass
class ScenarioTranslation:
    name: str
    description: str


@dataclass
class Scenario:
    id: str
    translations: Dict[str, ScenarioTranslation]
    interventions: list
    variables: dict = None

    @property
    def name(self):
        locale = get_locale()
        if locale is None:
            locale = DEFAULT_LOCALE
        else:
            locale = locale.language
        return self.translations[locale].name.strip()

    @property
    def description(self):
        locale = get_locale()
        if locale is None:
            locale = DEFAULT_LOCALE
        else:
            locale = locale.language
        return self.translations[locale].description.strip()


SCENARIOS = []
SCENARIOS.append(Scenario(
    id='default',
    translations={
        'fi': ScenarioTranslation(
            name='Nykymeno', description='''
            Säilytetään nykyiset rajoitukset ja testauskäytäntö.
            '''
        ),
        'en': ScenarioTranslation(
            name='Present interventions', description='''
            Current mobility restrictions and testing policy remain.
            '''
        ),
    },
    interventions=[],
    variables={
        'simulation_days': 360
    }
))


SCENARIOS.append(Scenario(
    id='summer-boogie',
    translations={
        'fi': ScenarioTranslation(
            name='Kesähöllennys', description='''
            Höllennetään nykyisiä rajoituksia hieman toukokuun puolivälistä lähtien.
            Väestö liikkuu 40% enemmän.
            ''',
        ),
        'en': ScenarioTranslation(
            name='Summer easing', description='''
            Ease current mobility restrictions somewhat starting from mid-May.
            Population will move 40% more.
            ''',
        ),
    },
    interventions=[
        ['limit-mobility', '2020-05-15', 30],
    ],
))

SCENARIOS.append(Scenario(
    id='hammer-and-testing',
    translations={
        'fi': ScenarioTranslation(
            name='Moukari ja suurennuslasi', description='''
            Säilytetään nykyiset rajoitukset, mutta laajennetaan testausta kaikkiin oirehtiviin
            ja jäljitetään tartuntaketjuja.
            ''',
        ),
        'en': ScenarioTranslation(
            name='Hammer and magnifying glass', description='''
            Current mobility restrictions remain, but change testing policy to test
            people even with mild symptoms and perform contact tracing.
            ''',
        ),
    },
    interventions=[
        ['test-with-contact-tracing', '2020-05-01']
    ],
))

SCENARIOS.append(Scenario(
    id='hammer-and-dance',
    translations={
        'fi': ScenarioTranslation(
            name='Moukari ja tanssi',
            description='''
            Laajennetaan testausta, tehdään kontaktien jäljitystä ja tasapainotellaan rajoitusten kanssa.
            ''',
        ),
        'en': ScenarioTranslation(
            name='Hammer and dance',
            description='''
            Test all people with even mild symptoms, perform contact tracing, and start a
            balancing act with mobility restrictions.
            ''',
        )
    },
    interventions=[
        ['test-with-contact-tracing', '2020-05-01'],
        ['limit-mobility', '2020-05-01', 20],
        ['limit-mobility', '2020-06-24', 40],
        ['limit-mobility', '2020-08-15', 20],
        ['limit-mobility', '2020-10-01', 30],
    ],
))
