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

Alternatively, you can run Reina with [Docker](https://www.docker.com/). To start with, build the image (this will take a while):

```
docker build . -t reina
```

Then you can start a container that runs Dash visualizations, at localhost:8123:

```
docker run -p 127.0.0.1:8123:8123 --name reina --rm -v $(pwd):/app reina
```

While the container is running, you can run the simulation like this:

```
docker exec -ti reina python -m calc.simulation
```

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
