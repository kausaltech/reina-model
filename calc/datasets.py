from dataclasses import dataclass

import pandas as pd

from utils import add_root_path, get_root_path

from . import calcfunc


@calcfunc()
def get_population():
    f = open(get_root_path() + '/data/005_11re_2018.csv', 'r', encoding='iso8859-1')
    f.readline()
    f.readline()
    df = pd.read_csv(f)
    df = df[(df.Alue != 'KOKO MAA') & (df['Ikä'] != 'Yhteensä')]
    df = df.rename(columns={
        'Miehet 2018 Väestö 31.12.': 'Male',
        'Naiset 2018 Väestö 31.12.': 'Female',
        'Alue': 'Area',
        'Ikä': 'Age',
    })
    df['Age'] = df['Age'].replace('100 -', '100').astype(int)
    return df.set_index('Area')


@calcfunc()
def get_healthcare_districts():
    p = get_root_path() + '/data/shp_jasenkunnat_2020.xls'
    df = pd.read_excel(p, header=3, sheet_name='shp_jäsenkunnat_2020_lkm')
    df = df[['kunta', 'sairaanhoitopiiri', 'erva-alue']].dropna()
    return df


@calcfunc(variables=['area_name'])
def get_population_for_area(variables):
    df = get_healthcare_districts()
    muni_names = df[df['sairaanhoitopiiri'] == variables['area_name']]['kunta'].unique()
    df = get_population()
    df = df[df.index.isin(muni_names)]
    df = df.reset_index().drop(columns='Area').groupby(['Age']).sum()
    return df


@calcfunc(variables=['country', 'max_age'])
def get_contacts_for_country(variables):
    f = open(get_root_path() + '/data/contact_matrix.csv', 'r')
    max_age = variables['max_age']

    df = pd.read_csv(f, header=0)
    df = df[df.country == variables['country']].drop(columns='country')

    df['place_type'] = df['place_type'].map(lambda x: x.replace('cnt_', '').replace('otherplace', 'other'))
    s = '-%d' % max_age
    df['participant_age'] = df['participant_age'].map(lambda x: x.replace('+', s))
    last_col = [x for x in df.columns if '+' in x]
    assert len(last_col) == 1
    df = df.rename(columns={last_col[0]: last_col[0].replace('+', s)})

    return df


AREA_CASEFILES = {
    'HUS': add_root_path('data/hosp_cases_hus.csv'),
    'Varsinais-Suomi': add_root_path('data/hosp_cases_varsinais-suomi.csv')
}

@calcfunc(
    variables=['area_name'],
    filedeps=list(AREA_CASEFILES.values())
)
def get_detected_cases(variables):
    area_name = variables['area_name']
    assert area_name in AREA_CASEFILES

    casefile = AREA_CASEFILES[area_name]
    df = pd.read_csv(casefile, header=0)
    df['date'] = pd.to_datetime(df['date']).dt.date
    df = df.set_index('date')
    return df



@dataclass
class InitialPopulationCondition:
    dead: int = 0
    in_icu: int = 0
    in_ward: int = 0
    confirmed_cases: int = 0
    infected_cases: int = 0
    incubating: int = 0
    ill: int = 0
    recovered: int = 0

    def were_incubating(self):
        """
        The number of people who contracted the virus at some point before simulation start
        """
        return sum([self.dead, self.recovered, self.in_icu, self.in_ward, self.ill, self.incubating])

    def recovered_without_illness(self):
        return self.were_incubating() - self.were_ill()

    def were_ill(self):
        """
        The number of people who contracted the virus and became ill at some point
        before simulation start
        """
        return sum([self.dead, self.recovered, self.in_icu, self.in_ward, self.ill])



@calcfunc(
    variables=['area_name', 'start_date', 'incubating_at_simulation_start',
               'ill_at_simulation_start', 'recovered_at_simulation_start'],
    filedeps=list(AREA_CASEFILES.values())
)
def get_initial_population_condition(variables) -> InitialPopulationCondition:
    area_name = variables['area_name']
    assert area_name in AREA_CASEFILES

    start_date = variables['start_date']

    casefile = AREA_CASEFILES[area_name]
    df = pd.read_csv(casefile, header=0, index_col=0)
    try:
        ds = df.loc[start_date]
    except (ValueError, KeyError) as e:
        print(f"Date {start_date} not found in {casefile} casefile,"
              " using zero infections for initial epidemic conditions")
        return InitialPopulationCondition()

    # These numbers we get from casefile
    dead = ds.at['dead']
    in_icu = ds['in_icu']
    in_ward = ds['in_ward']
    confirmed_cases = ds['confirmed']

    # These numbers are unmeasured and unmeasurable, they are given to simulation as
    # variables
    incubating = variables['incubating_at_simulation_start']
    ill = variables['ill_at_simulation_start']
    recovered = variables['recovered_at_simulation_start']

    return InitialPopulationCondition(
        dead=dead, in_icu=in_icu, in_ward=in_ward,
        confirmed_cases=confirmed_cases,
        ill=ill, incubating=incubating, recovered=recovered)





if __name__ == '__main__':
    ic = get_initial_population_condition()
    print(ic)
    exit()

    f = open(get_root_path() + '/data/hospitalizations_fin.csv', 'r')
    hdf = pd.read_csv(f, header=0).set_index('date')
    hdf = (hdf * ratio).dropna().astype(int)
    df['hospitalized'] = hdf['hospitalized']


    df = get_contacts_for_country()
    print(df)
    # print(df.sum(axis=0))
