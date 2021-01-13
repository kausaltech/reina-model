FROM python:3.8

RUN apt update && apt install -y libfreetype6-dev libpng-dev libqhull-dev pkg-config \
    gcc gfortran libopenblas-dev liblapack-dev cython

RUN mkdir /app /src
WORKDIR /app

COPY requirements.txt requirements-prod.txt /app/
RUN pip install -r requirements.txt -r requirements-prod.txt

COPY . /app
COPY ./docker/docker-entrypoint.sh /

RUN export PYTHONPATH="${PYTHONPATH}:/src"
RUN pybabel compile -d locale
RUN python -m cythonsim.build

EXPOSE 5000
ENTRYPOINT ["/bin/sh", "/docker-entrypoint.sh"]
