from typing import Dict
from dataclasses import dataclass
from variables import reset_variables, get_variable, set_variable
from flask_babel import get_locale


DEFAULT_LOCALE = 'en'


@dataclass
class ScenarioTranslation:
    name: str
    description: str


class Scenario:
    id: str
    translations: Dict[str, ScenarioTranslation]
    interventions: list
    variables: dict

    def __init__(self):
        if not hasattr(self, 'variables'):
            self.variables = {}
        if not hasattr(self, 'interventions'):
            self.interventions = []

    def get_translated(self, attr):
        locale = get_locale()
        if locale is None:
            locale = DEFAULT_LOCALE
        else:
            locale = locale.language
        return getattr(self.translations[locale], attr).strip()

    def get_name(self):
        return self.get_translated('name')

    def get_description(self):
        return self.get_translated('description')

    def apply(self):
        reset_variables()
        ivs = get_variable('interventions')
        if self.interventions:
            ivs += self.interventions
            set_variable('interventions', ivs)

        if self.variables:
            for key, val in self.variables.items():
                set_variable(key, val)

        set_variable('preset_scenario', self.id)


class DefaultScenario(Scenario):
    id = 'default'
    translations = {
        'fi': ScenarioTranslation(
            name='Nykyiset rajoitukset', description='''
            Säilytetään nykyiset rajoitukset ja testauskäytäntö.
            '''
        ),
        'en': ScenarioTranslation(
            name='Present interventions', description='''
            Current mobility restrictions and testing policy remain.
            '''
        ),
    }
    interventions = []


class MitigationScenario(Scenario):
    id = 'mitigation'
    translations = {
        'fi': ScenarioTranslation(
            name='Tehohoidon varmistaminen', description='''
            Varmistetaan sairaanhoidon kapasiteetti liikkuvuusrajoituksilla ja rakennetaan
            lisää tehohoitokapasiteettia.
            '''
        ),
        'en': ScenarioTranslation(
            name='Mitigation only', description='''
            Ensure that healthcare capacity is sufficient by
            '''
        ),
    }
    interventions = [
        ['build-new-icu-units', '2020-06-30', 150],
        ['build-new-icu-units', '2020-07-15', 150],
        ['build-new-icu-units', '2020-07-30', 150],
        ['build-new-icu-units', '2020-08-15', 150],
        ['build-new-icu-units', '2020-08-30', 150],
        ['limit-mobility', '2020-06-15', 20],
        ['limit-mobility', '2020-07-15', 30],
        ['limit-mobility', '2020-08-15', 25],
        ['limit-mobility', '2020-09-15', 40],
        ['limit-mobility', '2020-11-15', 20],
        ['limit-mobility', '2020-12-15', 40],
    ]


class SummerEasingScenario(Scenario):
    id = 'summer-boogie'
    translations = {
        'fi': ScenarioTranslation(
            name='Kesähöllennys', description='''
            Höllennetään nykyisiä rajoituksia hieman toukokuun puolivälistä lähtien.
            Rajoitukset pudotetaan 50%:ista 30%:iin. Säilytetään nykyinen testauskäytäntö,
            ei tehdä kontaktiketjujen määritystä.
            ''',
        ),
        'en': ScenarioTranslation(
            name='Summer easing', description='''
            Ease current mobility restrictions somewhat starting from mid-May.
            Restictions will be eased from 50% to 30%.
            ''',
        ),
    }
    interventions = [
        ['limit-mobility', '2020-05-15', 30],
    ]


class HammerDanceScenario(Scenario):
    id = 'hammer-and-dance'
    translations = {
        'fi': ScenarioTranslation(
            name='Nopea hybridimalli',
            description='''
            Laajennetaan testausta, tehdään kontaktien jäljitystä ja tasapainotellaan rajoitusten kanssa.
            ''',
        ),
        'en': ScenarioTranslation(
            name='Fast hybrid model',
            description='''
            Test all people with even mild symptoms, perform contact tracing, and start a
            balancing act with mobility restrictions.
            ''',
        )
    }
    interventions = [
        ['test-with-contact-tracing', '2020-05-01'],
        ['build-new-icu-units', '2020-06-30', 50],
        ['build-new-icu-units', '2020-07-30', 50],
        ['build-new-icu-units', '2020-08-30', 50],
        ['build-new-icu-units', '2020-09-30', 50],
        ['limit-mobility', '2020-05-01', 10],
        ['limit-mobility', '2020-06-24', 25],
        ['limit-mobility', '2020-08-15', 20],
        ['limit-mobility', '2020-09-01', 15],
        ['limit-mobility', '2020-12-06', 25],
    ]


class RetrospectiveEasingScenario(Scenario):
    id = 'looser-restrictions-to-start-with'
    translations = {
        'fi': ScenarioTranslation(
            name='Ruotsin polku',
            description='''
            Mitä jos alusta lähtien oltaisiinkin otettu puolet vähemmän liikkuvuuden rajoituksia käyttöön?
            '''
        ),
        'en': ScenarioTranslation(
            name='Followed Sweden',
            description='''
            What if we had taken half of the mobility restriction measures to start with?
            '''
        )
    }

    def apply(self):
        super().apply()

        ivs = get_variable('interventions')
        out = []
        for iv in ivs:
            iv = list(iv)
            if iv[0] == 'limit-mobility':
                iv[2] = iv[2] // 2
            out.append(iv)
        set_variable('interventions', out)


SCENARIOS = [
    DefaultScenario(),
    MitigationScenario(),
    SummerEasingScenario(),
    HammerDanceScenario(),
    RetrospectiveEasingScenario(),
]
