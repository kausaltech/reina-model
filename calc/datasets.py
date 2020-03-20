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


if __name__ == '__main__':
    print(get_population_for_healthcare_district('HUS'))
