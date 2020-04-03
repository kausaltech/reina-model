## How does the simulation work?

The simulation iterates through every member (agent) of the population once
every day of the simulation. The agents will be in one of the following states
throughout the epidemic: `susceptible`, `incubation`, `illness`, `hospitalized`,
`in ICU`, `dead` and `recovered`.

Factors such as the person's age, the contact matrix for the country,
public mobility limitations, testing practices, and available healthcare
capacity will have influence how the state transitions work.

This is a development version of the simulation tool. It is published with an
open source license, and you can look at [source code in GitHub](https://github.com/kausaltech/corona-agent-simulation).

You can also participate in [conversations about the development of the model](https://korona.kausal.tech/c/forecasting/7?locale=en).

## How does it compare to other COVID-19 epidemic models?

Most of the models are deterministic compartmental models such as SIR or SEIR.
Those models are good for getting a general understanding on the spread of the
epidemic, but extending these models with refined rules becomes complex quickly.

Our model is based on simulating interactions on an individual level, so arbitrary
rules can be evaluated easily. It also allows examining the features of the pathogen
(such as contagiousness and lethality) and the features of the population
(such as the number of close contacts per day) separately. Consequently, some important
parameters like the reproduction number R, are emergent properties that yield their
value during the simulation.

## How can I try it out in my geographical area?

We haven't yet implemented the user interface to select another geographical
area for analysis. It is not very difficult to do, so you can just
ask us by [posting on the forum](https://korona.kausal.tech/c/forecasting/7?locale=en)
or contacting the authors directly.

### Datasets

In order to apply the simulation in your area, you will need some area-specific
data. The model currently uses the following datasets:

#### Population age structure

The datasets contains the number of people for each age. Our dataset uses a resolution
of one year, but a grouped dataset (such as 60-69 years) could also be used.

#### Contact matrix

This dataset has the information on how many contacts per day and with what kind
of people each person has. It is provided as a two-dimensional matrix divided by
5-year age groups. We already have [the datasets for these
countries](https://github.com/kausaltech/corona-agent-simulation/blob/master/data/contact_matrix.csv):

- Belgium
- Germany
- Great Britain
- Finland
- Italy
- Luxembourg
- Netherlands
- Poland

Our data is based on the 2008 study
[Social Contacts and Mixing Patterns Relevant to the Spread of Infectious Diseases](https://journals.plos.org/plosmedicine/article?id=10.1371/journal.pmed.0050074). In the absence of research-based data,
you may approximate it in another country by applying the contact matrix for one
the countries in this list.

#### COVID-19 patients

We use the time-series data on the confirmed cases, hospitalisations, ICU usage and
deaths to validate the model.

#### Healthcare capacity

Currently, we only use the number of available hospital beds and ICU units.

## How to use the simulation?

You can simulate the effects of different events (or interventions) by adding
or removing them in the event list.

### Disease parameters

Some of the parameters related to the disease are still under discussion. You can
experiment how tuning the parameters changes the outcome of the simulation.

## Authors

[Jouni T. Tuomisto](mailto:jouni.tuomisto@kausal.tech), Finnish Institute for Health and Welfare, Kuopio, Finland

[Juha Yrjölä](mailto:juha.yrjola@kausal.tech), Kausal Ltd, Helsinki, Finland

[Mikko Kolehmainen](mailto:mikko.kolehmainen@uef.fi), University of Eastern Finland, Kuopio, Finland

[Juhani Bonsdorff](mailto:juhani.bonsdorff@gmail.com), Stretta Capital Oy, Helsinki, Finland

[Tero Tikkanen](mailto:tero.tikkanen@kausal.tech), Kausal Ltd, Helsinki, Finland
