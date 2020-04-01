import pandas as pd
from utils import get_root_path
from . import calcfunc


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


MUNIS_BY_DISTRICT = {
    'HUS': [
        'Askola', 'Järvenpää', 'Lohja', 'Raasepori', 'Espoo', 'Karkkila',
        'Loviisa', 'Sipoo', 'Hanko', 'Kauniainen', 'Mäntsälä', 'Siuntio',
        'Helsinki', 'Kerava', 'Nurmijärvi', 'Tuusula', 'Hyvinkää', 'Kirkkonummi',
        'Pornainen', 'Vantaa', 'Inkoo', 'Lapinjärvi', 'Porvoo', 'Vihti'
    ]
}


@calcfunc(variables=['area_name'])
def get_population_for_area(variables):
    muni_names = MUNIS_BY_DISTRICT[variables['area_name']]
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
    df = df[df.type == 'all'].drop(columns='type')

    df = df.set_index(['age of contact'])
    df.columns.name = 'age group of participant'

    df = df.sum(axis=0)

    ages = []
    counts = []
    for age_group, count in df.items():
        if age_group == '70+':
            start, end = 70, variables['max_age']
        else:
            start, end = map(int, age_group.split('-'))
        for age in range(start, end + 1):
            ages.append(age)
            counts.append(count)

    return pd.Series(counts, index=ages)


@calcfunc(variables=['area_name'])
def get_detected_cases(variables):
    area_name = variables['area_name']
    f = open(get_root_path() + '/data/cases_fin.csv', 'r')
    df = pd.read_csv(f, header=0).set_index('date')

    cdf = df[['district', 'confirmed']].reset_index().set_index(['date', 'district']).unstack('district')
    cdf['total'] = cdf.sum(axis=1)
    ratio = cdf[('confirmed', area_name)] / cdf['total']
    ratio = ratio.iloc[-1]
    df = df[df.district == area_name].drop(columns='district')

    f = open(get_root_path() + '/data/hospitalizations_fin.csv', 'r')
    hdf = pd.read_csv(f, header=0).set_index('date')
    hdf = (hdf * ratio).dropna().astype(int)
    df['hospitalized'] = hdf['hospitalized']
    df['in_icu'] = hdf['in_icu']

    return df


if __name__ == '__main__':
    df = get_contacts_for_country()
    print(df)
    # print(df.sum(axis=0))
