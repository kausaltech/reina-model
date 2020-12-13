FROM python:3.8

RUN apt update && apt install -y libfreetype6-dev libpng-dev libqhull-dev pkg-config \
    gcc gfortran libopenblas-dev liblapack-dev cython

RUN mkdir /app /src
WORKDIR /app
COPY . /app

# We check out editable installs (numpy) to /src, so that we can
# mount development directory to /app if we want,
# and numpy won't be suddenly missing. By default, numpy would be
# installed to /app/src
RUN pip install -r requirements.txt --src /src
RUN export PYTHONPATH="${PYTHONPATH}:/src"


RUN pybabel compile -d locale

EXPOSE 5000
ENTRYPOINT ["flask", "run", "--host=0.0.0.0", "--port=5000"]
