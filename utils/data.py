import pandas as pd


def find_consecutive_start(values):
    last_val = start_val = values[0]
    for val in values[1:]:
        if val - last_val != 1:
            start_val = val
        last_val = val
    return start_val


def get_contributions_from_multipliers(df, a_column, ef_column, a_contributors=[]):
    hdf = df[~df.Forecast]
    fdf = df[df.Forecast]

    # Values from reference year
    ref = hdf.loc[hdf.index.max(), [a_column, ef_column]]
    ref_product = ref.product()

    # We allocate the reduction shares by first calculating
    # emissions assuming that the emission factor stays the same
    # as the last historical value. The rest of the reductions we
    # allocate to emission factor.
    a_part = (ref_product - fdf[a_column] * ref[ef_column]).clip(lower=0)
    total = ref_product - fdf[a_column] * fdf[ef_column]
    ef_part = (total - a_part).clip(lower=0)

    ef_part = ef_part / total
    a_part = 1 - ef_part

    total.name = 'EmissionReductions'

    out = pd.DataFrame(index=total.index)
    out['EmissionReductions'] = total
    out[a_column] = a_part
    out[ef_column] = ef_part

    if a_contributors:
        a_change = (-(df[a_column] - ref[a_column])).clip(lower=0)
        for col in a_contributors:
            out[col] = (df[col] / a_change) * out[a_column]

    return out
