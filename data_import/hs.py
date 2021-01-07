import pandas as pd

import requests
from calc.datasets import get_healthcare_districts, get_population

import requests_cache
requests_cache.install_cache('hs')


def get_deaths():
    resp = requests.get('https://w3qa5ydb4l.execute-api.eu-west-1.amazonaws.com/prod/finnishCoronaData/v2')
    data = resp.json()

    """
    conf = data['confirmed']
    df = pd.DataFrame.from_records(conf)
    df.date = pd.to_datetime(df.date)
    s1 = df.groupby([pd.Grouper(key='date', freq='d'), 'healthCareDistrict'])['id'].count()
    s1.name = 'confirmed'
    """

    deaths = data['deaths']
    df = pd.DataFrame.from_records(deaths)
    df.date = pd.to_datetime(df.date)
    s = df.groupby([pd.Grouper(key='date', freq='d'), 'area'])['id'].count()
    s.name = 'deaths'
    df = s.reset_index()
    df.date = df.date.dt.date
    df = df.set_index(['date', 'area'])['deaths']
    df = df.unstack('area').fillna(0).cumsum().astype(int)
    return df

    """
    df = pd.concat([s1], axis=1)

    df = df.reset_index()
    df.date = df.date.dt.date
    df = df.rename(columns=dict(healthCareDistrict='district'))
    df = df.set_index(['date', 'district']).unstack('district')
    df = df.fillna(0).cumsum().stack('district').astype(int).reset_index('district')

    return deaths
    """


def get_hospitalisations():
    resp = requests.get('https://w3qa5ydb4l.execute-api.eu-west-1.amazonaws.com/prod/finnishCoronaHospitalData')
    data = resp.json()['hospitalised']

    df = pd.DataFrame.from_records(data)
    df.date = pd.to_datetime(df.date).dt.date
    df = df[['date', 'area', 'dead', 'inIcu', 'inWard', 'totalHospitalised']]

    df = df.rename(columns=dict(inIcu='in_icu', inWard='in_ward', totalHospitalised='hospitalized'))
    df = df.set_index('date')
    return df


if __name__ == '__main__':
    # ERVA = 'HYKS'
    # SHP = 'HUS'
    RATIO_OVERRIDE = None
    MUNI = None

    ERVA = 'TYKS'
    SHP = 'Varsinais-Suomi'
    if False:
        MUNI = 'Turku'
        RATIO_OVERRIDE = 0.50
    else:
        MUNI = None

    pops = get_population()

    df = get_healthcare_districts()

    catchment_area_munis = df[df['erva-alue'] == ERVA].kunta.unique()
    catchment_area_pop = pops[pops.index.isin(catchment_area_munis)][['Male', 'Female']].sum().sum()

    if SHP:
        area_munis = df[df['sairaanhoitopiiri'] == SHP].kunta.unique()
        area_pop = pops[pops.index.isin(area_munis)][['Male', 'Female']].sum().sum()
        target_area = SHP
    else:
        area_pop = pops[pops.index == MUNI][['Male', 'Female']].sum().sum()
        target_area = MUNI

    if not RATIO_OVERRIDE:
        ratio = area_pop / catchment_area_pop
    else:
        ratio = RATIO_OVERRIDE

    print('Ratio %.2f %%' % (ratio * 100))

    df = get_deaths()
    print(df)

    df = get_hospitalisations()
    df = df[df['district'] == SHP]
    confirmed = df['confirmed']

    df = get_hospital_data()
    df = df[df['area'] == ERVA].set_index('date').drop(columns='area')

    # erva is a larger area than an shp, so we scale by population ratios
    df *= ratio
    df = df.iloc[:-1]

    df = df.reindex(confirmed.index, method='pad')
    df['confirmed'] = confirmed
    df = df[df['confirmed'] > 0].fillna(0).astype(int)

    df.to_csv('data/hosp_cases_%s.csv' % SHP.lower())
    exit()
