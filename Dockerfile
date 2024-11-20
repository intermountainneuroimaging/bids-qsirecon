
FROM pennlinc/qsirecon:0.23.2 as base
LABEL maintainer="Amy Hegarty <amy.hegarty@colorado.edu>"

#ENV HOME=/root/

ENV FLYWHEEL="/flywheel/v0"
WORKDIR ${FLYWHEEL}

# Install git to run pre-commit hooks inside container
RUN apt-get update &&\
    apt-get install -y --no-install-recommends \
	 git \
     zip \
     unzip  \
     time &&\
	apt-get update &&\
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# install vendored poetry
ENV POETRY_VERSION=1.8.4 \
    # make poetry install to this location
    POETRY_HOME="/opt/poetry" \
    # do not ask any interactive questions
    POETRY_NO_INTERACTION=1 \
    VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
RUN python3 -m pip install --upgrade pip && \
    ln -sf /opt/conda/envs/qsiprep/bin/python3 /opt/venv/bin/python3
ENV PATH="$POETRY_HOME/bin:$PATH"
#ENV POETRY_VIRTUALENVS_CREATE="false"

# get-poetry respects ENV
RUN curl -sSL https://install.python-poetry.org | python3 - ; \
    chmod +x "$POETRY_HOME/bin/poetry"
#
## Installing main dependencies
COPY pyproject.toml poetry.lock $FLYWHEEL/
RUN poetry install --no-root --no-dev
#
# Create Flywheel User
RUN adduser --disabled-password --gecos "Flywheel User" flywheel
# Installing the current project (most likely to change, above layer can be cached)
COPY ./ $FLYWHEEL/
#RUN pip install --no-cache-dir .
#
## Configure entrypoint
RUN chmod a+x $FLYWHEEL/run.py
ENTRYPOINT ["poetry","run","python","/flywheel/v0/run.py"]
