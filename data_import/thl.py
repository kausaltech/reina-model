import json
import re
import pandas as pd
import numpy as np
from collections import OrderedDict

import requests
from pyjstat import pyjstat


BASE_URL = 'https://sampo.thl.fi/pivot/prod/fi/'
VACC_PATH = 'vaccreg/cov19cov/fact_cov19cov'
CASE_PATH = 'epirapo/covid19case/fact_epirapo_covid19case'

#BASE_URL = 'https://sampo.thl.fi/pivot/prod/fi/epirapo/covid19case/fact_epirapo_covid19case.json'
DIMENSIONS_BASE_URL = 'https://sampo.thl.fi/pivot/prod/fi/epirapo/covid19case/fact_epirapo_covid19case.dimensions.json'
REQUESTS_HEADERS = {
    'User-Agent': 'curl/7.63.0'
}


def process_children(d):
    out = {}
    out['id'] = d.pop('id')
    out['label'] = d.pop('label')
    out['sid'] = d.pop('sid', None)
    out['children'] = {}
    if d['children']:
        for c in d['children']:
            pass


def get_dimensions(path):
    resp = requests.get(
        BASE_URL + path + '.dimensions.json',
        headers=REQUESTS_HEADERS,
    )
    resp.raise_for_status()
    text = re.sub(r'([a-zA-Z_0-9\.]*\()|(\);?$)','', resp.text).strip()
    data = json.loads(text)
    out = {}
    for d in data:
        o = {}
        out['label'] = d.pop('label')
        o['children'] = d['children']
        c = d['children'][0]
        c.pop('children')
        out[d.pop('id')] = o
    return data


def get_data(path, rows, columns, filters=None, measure=None):
    if isinstance(rows, str):
        rows = [rows]
    if isinstance(columns, str):
        columns = [columns]
    if isinstance(filters, str):
        filters = [filters]

    params = dict(row=','.join(rows), column=','.join(columns))
    if filters:
        params['filter'] = ','.join(filters)

    resp = requests.get(
        BASE_URL + path + '.json',
        params=params,
        headers=REQUESTS_HEADERS,
    )
    resp.raise_for_status()

    out = resp.json(object_pairs_hook=OrderedDict)['dataset']
    out['id'] = out['dimension']['id']
    for dim_name in out['id']:
        out['dimension'][dim_name]['label'] = None

    df = pyjstat.generate_df(out, 'label')
    return df


def get_case_data(rows, columns, measure=None, filters=None):
    return get_data(CASE_PATH, rows, columns, filters=filters, measure=measure)


def get_vacc_data(rows, columns, measure=None, filters=None):
    return get_data(VACC_PATH, rows, columns, filters=filters)


def process_value_column(s):
    s = s.map(lambda x: np.nan if x == '..' else x)
    return s.astype(float).astype('Int64')


def process_weekly_data(df):
    df = df[df['dateweek20200101'] != 'Kaikki ajat'].copy()
    df['date'] = pd.to_datetime(
        df['dateweek20200101'].map(lambda x: x + '-7' if x != 'Time' else x),
        format='Vuosi %G Viikko %V-%u', errors='coerce'
    ).dt.date
    df = df.dropna()
    s = df.set_index(['date', 'hcdmunicipality2020'])['value']
    s = process_value_column(s)
    df = s.unstack('hcdmunicipality2020')
    return df


def get_weekly_current_totals(df):
    df = df[df['dateweek20200101'] == 'Kaikki ajat'].copy()
    s = df.set_index('hcdmunicipality2020')['value']
    return process_value_column(s)


def get_vaccinations(area_name):
    df = get_vacc_data(rows=['area-518349', 'dateweek20201226-525425'], columns='cov_vac_age-518413')
    df = df[df['dateweek20201226'] != 'Kaikki ajat'].copy()
    df = df[df['cov_vac_age'] != 'Kaikki iät']
    df['date'] = pd.to_datetime(
        df['dateweek20201226'].map(lambda x: x + '-7' if x != 'Time' else x),
        format='Vuosi %G Viikko %V-%u', errors='coerce'
    ).dt.date

    df = df[df['area'] == area_name]

    s = df.set_index(['date', 'area', 'cov_vac_age'])['value']
    s = process_value_column(s)
    df = s.unstack('cov_vac_age')
    df = df.reset_index('area').drop(columns='area')
    return df


def get_daily_data(row, measure=None):
    df = get_case_data(row, 'dateweek20200101-508804L', filters=measure)
    df['date'] = pd.to_datetime(df['dateweek20200101']).dt.date
    df = df.dropna()
    s = df.set_index(['date', 'hcdmunicipality2020'])['value']
    s = process_value_column(s)
    df = s.unstack('hcdmunicipality2020')
    return df


def get_weekly_data(row, measure=None):
    df = get_case_data(row, 'dateweek20200101-509030')
    totals = get_weekly_current_totals(df)
    df = process_weekly_data(df)
    return df, totals


if True:
    pd.set_option('display.max_rows', None)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)
    pd.set_option('display.max_colwidth', None)


def get_hcd_cases():
    return get_daily_data('hcdmunicipality2020-445222')


def get_muni_cases(hcd_name, muni_name):
    hcd, hcd_totals = get_weekly_data('hcdmunicipality2020-445222')
    muni, muni_totals = get_weekly_data('hcdmunicipality2020-445257L')

    muni = muni[muni_name]
    hcd = hcd[hcd_name]
    hcd.name = 'hcd'

    df = pd.DataFrame(hcd)
    df['muni'] = muni
    df = df.dropna()
    df['ratio'] = df['muni'] / df['hcd']
    df['ratior'] = df['ratio'].rolling(window=4).mean()
    weekly_df = df

    daily = get_daily_data('hcdmunicipality2020-445222')
    hcd = daily[hcd_name]
    hcd.name = 'hcd'
    df = pd.DataFrame(hcd).dropna()
    df = df[df.index >= '2020-03-01'].copy()

    df['ratio'] = weekly_df['ratior']
    df['ratio'] = df['ratio'].interpolate()
    df['ratio'] = df['ratio'].fillna(method='backfill')

    s = weekly_df['muni']
    s = s.fillna(0).cumsum()
    total = muni_totals[muni_name]
    s /= s.iloc[-1] / total
    s = s.astype(int)
    df['munisum'] = s
    df.loc[df.index[0], 'munisum'] = np.nan
    df.loc[df.index[-1], 'munisum'] = total
    df['emuni'] = df['hcd'] * df['ratio']
    df['emunisum'] = df['emuni'].cumsum()
    df['fix'] = df['emunisum'] / df['munisum']

    last_day = df.index[0]
    for day, val in df['fix'].dropna().items():
        df.loc[(df.index > last_day) & (df.index <= day), 'emunisum'] /= val
        last_day = day

    df['emunisum'] = df['emunisum'].astype(int).cummax()

    df['muni_cases'] = df['emunisum'].astype(int)
    df['hcd_cases'] = df['hcd'].cumsum()
    df = df[['hcd_cases', 'muni_cases']]

    return df


def get_country_muni_cases():
    daily = get_daily_data('hcdmunicipality2020-445222').sum(axis=1)
    return daily


if __name__ == '__main__':
    import requests_cache; requests_cache.install_cache('thl')


    if True:
        # print(get_dimensions(VACC_PATH))
        # df = get_vacc_data(rows='area-518349', columns='cov_vac_age-518413', filters='dateweek20201226-531437')
        #df = get_vacc_data(rows=['area-518349', 'dateweek20201226-525425'], columns='cov_vac_age-518413')
        df = get_vaccinations('Turku')
        print(df)
        exit()

    if True:
        df = get_country_muni_cases()
        df = df.groupby(pd.Grouper(freq='W')).mean()
        df /= df.mean()
        for date, val in zip(df.index, df.values):
            print('%s\t%s' % (str(date).split(' ')[0], str(val).replace('.', ',')))

    if False:
        print(get_muni_cases('Varsinais-Suomen SHP', 'Turku'))
