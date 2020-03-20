import warnings
import pandas as pd

# Disable Pint's old fallback behavior (must come before importing Pint)
import os
os.environ['PINT_ARRAY_PROTOCOL_FALLBACK'] = "0"
from pint import UnitRegistry  # noqa

ureg = UnitRegistry()
Q = ureg.Quantity


# Silence NEP 18 warning
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    Q([])


def convert_units(series, from_unit, to_unit):
    arr = Q(series.values, from_unit).to(to_unit).m
    return pd.Series(arr, index=series.index, name=series.name)
