import os
from datetime import datetime

import requests
from dateutil.parser import parse as parse_dt
from dateutil.tz import tzlocal

from utils.data import get_dataset_path


URL = 'https://www.gstatic.com/covid19/mobility/Region_Mobility_Report_CSVs.zip'

DATASET_ZIP_NAME = 'Google_Region_Mobility_Report_CSVs.zip'


def download_updated_zip():
    resp = requests.head(URL)
    resp.raise_for_status()
    lm = resp.headers['last-modified']
    dt = parse_dt(lm)
    zip_fn = os.path.join(get_dataset_path(), DATASET_ZIP_NAME)
    try:
        zip_dt = datetime.fromtimestamp(os.path.getmtime(zip_fn), tzlocal())
    except FileNotFoundError:
        zip_dt = None
    if zip_dt is not None and dt <= zip_dt:
        return zip_fn
    print('Downloading updated ZIP: %s' % DATASET_ZIP_NAME)
    resp = requests.get(URL)
    resp.raise_for_status()
    with open(zip_fn, 'wb') as zipf:
        zipf.write(resp.content)
        zipf.close()
    return zip_fn


if __name__ == '__main__':
    download_updated_zip()
