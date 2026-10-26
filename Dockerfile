FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv

COPY requirements.txt .
RUN pip install -r requirements.txt

RUN useradd --create-home --uid 1000 sire
COPY --chown=sire:sire app ./app
COPY --chown=sire:sire tests ./tests
COPY --chown=sire:sire sql ./sql
USER sire

# Flet en servidor Linux se levanta siempre en modo web
ENV FLET_SERVER_IP=0.0.0.0 \
    FLET_SERVER_PORT=8550
EXPOSE 8550

CMD ["python", "-m", "app.main"]
