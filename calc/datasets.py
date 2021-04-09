import os
from dataclasses import dataclass
from zipfile import ZipFile

import pandas as pd
from utils import add_root_path, get_root_path
from utils.data import get_dataset_path
from data_import.google_covid_mobility import DATASET_ZIP_NAME as MOBILITY_DATASET_FILENAME

from . import calcfunc


POPULATION_CSV_PATH = add_root_path('data/005_11re_2019.csv')


@calcfunc(
    filedeps=[POPULATION_CSV_PATH]
)
def get_population():
    f = open(POPULATION_CSV_PATH, 'r', encoding='iso8859-1')
    f.readline()
    f.readline()
    df = pd.read_csv(f, delimiter=';', quotechar='"')
    df = df[(df.Alue != 'KOKO MAA') & (df['Ikä'] != 'Yhteensä')]
    df = df.rename(columns={
        'Miehet 2019 Väestö 31.12.': 'Male',
        'Naiset 2019 Väestö 31.12.': 'Female',
        'Alue': 'Area',
        'Ikä': 'Age',
    })
    drop_cols = []
    for col in df.columns:
        if 'yhteensä' in col.lower():
            drop_cols.append(col)
    df = df.drop(columns=drop_cols)
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
    area = variables['area_name']
    df = get_population()
    if area not in df.index:
        # It's the name of a HCD
        hdf = get_healthcare_districts()
        muni_names = hdf[hdf['sairaanhoitopiiri'] == variables['area_name']]['kunta'].unique()
        df = df[df.index.isin(muni_names)]
    else:
        df = df[df.index == variables['area_name']]

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
    'Varsinais-Suomi': add_root_path('data/hosp_cases_varsinais-suomi.csv'),
    'Turku': os.path.join(get_dataset_path(), 'hosp_cases_turku.csv'),
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
    df = df.drop(columns='hospitalized').rename(columns=dict(confirmed='all_detected'))

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

    def has_initial_state(self):
        return (self.dead or self.in_icu or self.in_ward or self.confirmed_cases
                or self.infected_cases or self.incubating or self.ill or self.recovered)

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


MOBILITY_FILE_PATH = os.path.join(get_dataset_path(), MOBILITY_DATASET_FILENAME)


def read_mobility_file(fn, area_name):
    with ZipFile(MOBILITY_FILE_PATH) as zipf:
        with zipf.open(fn) as csvf:
            df = pd.read_csv(csvf, header=0, index_col='date')

    df = df.drop(columns=[
        'country_region_code', 'country_region', 'metro_area', 'iso_3166_2_code',
        'census_fips_code', 'place_id'
    ])
    REGIONS = {
        'HUS': (1, 'Uusimaa'),
        'Varsinais-Suomi': (1, 'Southwest Finland'),
        'Turku': (2, 'Turku'),
        'Helsinki': (2, 'Helsinki'),
        'Espoo': (2, 'Helsinki'),
    }
    region_id, region = REGIONS[area_name]
    if region_id == 1:
        df = df[(df['sub_region_1'] == region) & df.sub_region_2.isna()]
    elif region_id == 2:
        df = df[df['sub_region_2'] == region]

    df = df.drop(columns=['sub_region_1', 'sub_region_2'])
    renames = {x: x.replace('_percent_change_from_baseline', '') for x in df.columns}
    df = df.rename(columns=renames)
    df.index = pd.to_datetime(df.index)
    return df


@calcfunc(
    variables=['area_name', 'country'],
    filedeps=[MOBILITY_FILE_PATH]
)
def get_mobility_data(variables):
    csv_fn = '2020_%s_Region_Mobility_Report.csv' % variables['country']
    df1 = read_mobility_file(csv_fn, variables['area_name'])
    csv_fn = '2021_%s_Region_Mobility_Report.csv' % variables['country']
    df2 = read_mobility_file(csv_fn, variables['area_name'])

    return df1.append(df2)


@calcfunc(
    funcs=[get_mobility_data],
)
def generate_mobility_ivs():
    df = get_mobility_data()
    COLS = (
        ('retail_and_recreation', 'leisure'),
        ('workplaces', 'work'),
        ('transit_stations', 'transport'),
    )
    df = df.groupby(pd.Grouper(freq='W')).mean().interpolate().shift(-1).dropna().astype(int)

    ivs = []
    for col_name, con_name in COLS:
        last_val = None
        for date, val in df[col_name].iteritems():
            date_str = date.isoformat().split('T')[0]
            if date_str < '2020-03-08':
                continue
            if val > 0:
                continue
            if last_val is not None and abs(last_val - val) < 5:
                continue
            ivs.append(['limit-mobility', date.isoformat().split('T')[0], -val, None, None, con_name])
            last_val = val
    return ivs


VACCINATIONS_FILE_PATH = os.path.join(get_dataset_path(), 'fi_vaccinations.csv')

@calcfunc(
    variables=['area_name'],
    filedeps=[VACCINATIONS_FILE_PATH],
)
def generate_vaccination_ivs(variables):
    df = pd.read_csv(VACCINATIONS_FILE_PATH)
    df = df[df.area == variables['area_name']].drop(columns='area')
    df = df.fillna(0)
    df = df.set_index('date')
    # Drop the latest week because it will have incomplete data
    df = df.iloc[:-1]
    ivs = []
    for col_name in df.columns:
        if '-' in col_name:
            start_age, end_age = [int(x) for x in col_name.split('-')]
        elif col_name.endswith('+'):
            start_age, end_age = int(col_name.strip('+')), None

        for idx, val in df[[col_name]].itertuples():
            date_str = idx
            ivs.append(['vaccinate', date_str, int(val), start_age, end_age])

    return ivs

if __name__ == '__main__':
    df = generate_vaccination_ivs()
    exit()
    #df = get_detected_cases()
    #print(df)
    #exit()

    df = get_mobility_data()
    pd.set_option('display.max_rows', None)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)
    pd.set_option('display.max_colwidth', -1)
    print(df.rolling(window=7).mean())
    exit()

    f = open(get_root_path() + '/data/hospitalizations_fin.csv', 'r')
    hdf = pd.read_csv(f, header=0).set_index('date')
    hdf = (hdf * ratio).dropna().astype(int)
    df['hospitalized'] = hdf['hospitalized']


    df = get_contacts_for_country()
    print(df)
    # print(df.sum(axis=0))
