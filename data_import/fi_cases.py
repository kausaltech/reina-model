import os
import sys
from calc.datasets import get_healthcare_districts
from data_import.thl import get_data, get_muni_cases, get_hcd_cases
from data_import.hs import get_deaths, get_hospitalisations
from utils.data import get_dataset_path


def update_case_data(muni_name, hosp_multiplier):
    df = get_healthcare_districts()
    muni = df[df.kunta == muni_name].iloc[0]

    catchment_area = muni['erva-alue']
    hcd = muni['sairaanhoitopiiri']
    other_hcds = df[df['erva-alue'] == catchment_area]['sairaanhoitopiiri'].unique()

    HCD_TO_THL = {
        'Varsinais-Suomi': 'Varsinais-Suomen SHP',
        'Satakunta': 'Satakunnan SHP',
        'HUS': 'Helsingin ja Uudenmaan SHP',
        'Päijät-Häme': 'Päijät-Hämeen SHP',
    }

    df = get_hcd_cases()
    hcds = [HCD_TO_THL.get(x, '%sn SHP' % x) for x in other_hcds]
    ca_cases = df[hcds].sum(axis=1).astype(int).cumsum()

    df = get_muni_cases(HCD_TO_THL[hcd], muni_name)
    df['ca_cases'] = ca_cases

    df['muni_diff'] = df['muni_cases'].diff()
    df['ca_diff'] = df['ca_cases'].diff()
    df['ratio'] = (df['muni_diff'] / df['ca_diff']).clip(upper=1).interpolate()
    df['ratio'] = df['ratio'].rolling(window=14).mean().shift(14).fillna(method='bfill')

    df['ca_deaths'] = get_deaths()[catchment_area]
    df['ca_deaths'] = df['ca_deaths'].fillna(method='ffill').fillna(0).astype(int)
    hdf = get_hospitalisations()
    hdf = hdf[hdf.area == catchment_area][['in_icu', 'in_ward']]
    hdf = hdf[~hdf.index.duplicated()]
    df['ca_in_icu'] = hdf['in_icu']
    df['ca_in_ward'] = hdf['in_ward']

    df['ca_in_icu'] = df['ca_in_icu'].fillna(method='ffill').fillna(0).astype(int)
    df['ca_in_ward'] = df['ca_in_ward'].fillna(method='ffill').fillna(0).astype(int)

    df['in_icu'] = (df['ca_in_icu'] * df['ratio'] * hosp_multiplier).astype(int)
    df['in_ward'] = (df['ca_in_ward'] * df['ratio'] * hosp_multiplier).astype(int)
    df['dead'] = (df['ca_deaths'].diff() * df['ratio']).cumsum().fillna(0).astype(int)
    df = df.rename(columns=dict(hcd_cases='confirmed'))
    df['hospitalized'] = df['in_icu'] + df['in_ward']
    df = df[['dead', 'in_icu', 'in_ward', 'hospitalized', 'confirmed']]

    cases_path = os.path.join(get_dataset_path(), 'hosp_cases_%s.csv' % muni_name.lower())
    df.to_csv(cases_path, header=1)


if __name__ == '__main__':
    area = sys.argv[1]
    if area == 'Turku':
        mult = 1.0
    else:
        mult = 1.0
    update_case_data(sys.argv[1], mult)
