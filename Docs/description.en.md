### How does the simulation work?

The simulation iterates through every member (agent) of the population once
every day of the simulation. The agents will be in one of the following states
throughout the epidemic: `susceptible`, `incubation`, `illness`, `hospitalized`,
`in ICU`, `dead` and `recovered`.

Factors such as the person's age, the contact matrix for the country,
public mobility limitations, testing practices, and available healthcare
capacity will have influence how the state transitions work.

This is a development version of the simulation tool. It is published with an
open source license, and you can look at [source code in GitHub](https://github.com/kausaltech/corona-agent-simulation).

### How does it compare to other COVID-19 epidemic models?

Most of the models are deterministic compartmental models such as SIR or SEIR.
Those models are good for getting a general understanding on the spread of the
epidemic, but extending these models with refined rules becomes complex quickly.

Our model is based on simulating interactions on an individual level, so arbitrary
rules can be evaluated easily.

#### Events

You can simulate the effects of different events (or interventions) by adding
or removing them in the event list.
