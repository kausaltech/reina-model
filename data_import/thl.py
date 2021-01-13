import pandas as pd
import numpy as np
from collections import OrderedDict

import requests
from pyjstat import pyjstat


BASE_URL = 'https://sampo.thl.fi/pivot/prod/fi/epirapo/covid19case/fact_epirapo_covid19case.json'
DIMENSIONS_BASE_URL = 'https://sampo.thl.fi/pivot/prod/fi/epirapo/covid19case/fact_epirapo_covid19case.dimensions.json'
REQUESTS_HEADERS = {
    'User-Agent': 'curl/7.63.0'
}


def thl_get(rows, columns, measure=None):
    if isinstance(rows, str):
        rows = [rows]
    if isinstance(columns, str):
        columns = [columns]

    params = dict(row=','.join(rows), column=','.join(columns))
    if measure:
        params['filter'] = measure

    resp = requests.get(
        BASE_URL,
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


def process_value_column(s):
    s = s.map(lambda x: np.nan if x == '..' else x)
    return s.astype(float).astype('Int64')


def process_weekly_data(df):
    df = df[df['dateweek20200101'] != 'Aika'].copy()
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
    df = df[df['dateweek20200101'] == 'Aika'].copy()
    s = df.set_index('hcdmunicipality2020')['value']
    return process_value_column(s)


def get_daily_data(row, measure=None):
    df = thl_get(row, 'dateweek20200101-508804L', measure)
    df['date'] = pd.to_datetime(df['dateweek20200101']).dt.date
    df = df.dropna()
    s = df.set_index(['date', 'hcdmunicipality2020'])['value']
    s = process_value_column(s)
    df = s.unstack('hcdmunicipality2020')
    return df


def get_weekly_data(row, measure=None):
    df = thl_get(row, 'dateweek20200101-509030')
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
    df.loc[df.index[0], 'munisum'] = 0
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


if __name__ == '__main__':
    print(get_cases('Varsinais-Suomen SHP', 'Turku'))
