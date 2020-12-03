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

    cdf = df[['district', 'confirmed']].reset_index().set_index(['date', 'district']).unstack('district')
    cdf['total'] = cdf.sum(axis=1)
    ratio = cdf[('confirmed', area_name)] / cdf['total']
    ratio = ratio.iloc[-1]
    df = df[df.district == area_name].drop(columns='district')

    f = add_root_path('data/hospitalizations_fin.csv')
    hdf = pd.read_csv(f, header=0).set_index('date')
    hdf = (hdf * ratio).dropna().astype(int)
    df['hospitalized'] = hdf['hospitalized']
    df['in_icu'] = hdf['in_icu']
    df = df.dropna()

    return df


if __name__ == '__main__':
    get_detected_cases()
    exit()

    f = open(get_root_path() + '/data/hospitalizations_fin.csv', 'r')
    hdf = pd.read_csv(f, header=0).set_index('date')
    hdf = (hdf * ratio).dropna().astype(int)
    df['hospitalized'] = hdf['hospitalized']


    df = get_contacts_for_country()
    print(df)
    # print(df.sum(axis=0))
