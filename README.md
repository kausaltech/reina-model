# Agent-based COVID-19 simulation

This software implements an agent-based (or individual-based) model for simulating
the spread of the coronavirus (SARS-CoV-2) in a healthcare district.

It models healthcare capacity (hospital beds and ICU units) and different
public health simulations.

[More documentation](Docs/description.en.md) is also available in the repository.


## Installation

If you're using Ubuntu/Debian, you might need to install a couple of packages:

```
apt install python3.8-dev libpython3.8-dev python3.8-venv \
    libfreetype6-dev libpng-dev libqhull-dev pkg-config \
    gcc gfortran libopenblas-dev liblapack-dev cython
```

Install a Python venv with Python 3.7 or 3.8. Install the requirements:

```
pip install -r requirements.txt
```

Compile translations:

```
pybabel compile -d locale
```

## Usage

Run the simulation with:

```
python -m calc.simulation
```

Or visualize using Dash:

```
python -m corona
```

## Installing and running with Docker

You can run Reina with [Docker](https://www.docker.com/). Check `reina-ui`  project to `../reina-ui` and set following environment variables to `.env` file:
```
ENV=dev
FLASK_ENV=development
NEXT_PUBLIC_GRAPHQL_ENDPOINT=http://localhost:8080/graphql
```
Then run

```
docker-compose up
```

The first time you run it, it will build the container for Reina, which takes some time. Once build done, Reina UI is available at localhost:8080.

While the container is running, you can run the simulation like this:

```
docker exec -ti reina-model python -m calc.simulation
```

## Configuring the hospital district

Currently, Reina supports Helsinki and Uusimaa district (HUS) and Varsinais-Suomi hospital district out of the box. By default, it's configured to run for HUS, but you can set
the district as Varsinais-Suomi by setting the environment variable AREA_NAME as follows:
```
AREA_NAME=Varsinais-Suomi
```

If you're running your setup via docker-compose, you can set the environment variable
in `.env` file in the project root directory and it will work directly.

## Development

### Localisation

Extract new translation strings to the template:

```
pybabel extract -w 120 -F babel.cfg -o locale/messages.pot .
```

Merge new strings to language-specific translation files:

```
pybabel update -w 120 -i locale/messages.pot -d locale
```
