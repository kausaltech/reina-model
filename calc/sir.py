import numpy as np
import scipy.integrate
import pandas as pd

from . import calcfunc
from calc.datasets import get_population_for_area
from variables import set_variable, get_variable


def sir(infection_rate, recovery_rate, population):
    b = infection_rate
    l = recovery_rate
    N = population
    def model(t, SI):
        S, I = SI
        dS =  -b*I*S/N
        dI = b*I*S/N - l*I

        return [dS, dI]
    return model


@calcfunc(
    variables=['initial_infected', 'initial_recovered', 'simulation_days', 'r0', 'infectious_days'],
    funcs=[get_population_for_area],
)
def simulate_progress(variables):
    population = get_population_for_area().sum(axis=1).sum()

    days = np.arange(0, variables['simulation_days'])
    r0 = variables['r0']
    mean_duration = variables['infectious_days']
    initial_recovered = variables['initial_recovered']
    initial_infected = variables['initial_infected']

    recovery_rate = 1/mean_duration
    infection_rate = r0*recovery_rate
    model = sir(infection_rate, recovery_rate, population)

    initial_suspectible = population - initial_infected - initial_recovered
    solution = scipy.integrate.solve_ivp(model, days[[0, -1]], [initial_suspectible, initial_infected],
        t_eval=days, dense_output=True)
    
    suspectible, infected = solution.y
    recovered = population - suspectible - infected

    return pd.DataFrame(index=days, data=dict(
        suspectible=suspectible,
        infected=infected,
        recovered=recovered
    ))


if __name__ == '__main__':
    import matplotlib.pyplot as plt

    df = simulate_progress()
    initial_infected = get_variable('initial_infected')
    plt.plot(df)
    plt.legend()
    plt.show()
