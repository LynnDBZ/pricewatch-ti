FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
RUN pip install .

COPY config ./config
COPY tests/fixtures ./tests/fixtures

# Ejecutar sin privilegios de root
RUN useradd -m bot && mkdir -p data reports docs && chown -R bot:bot /app
USER bot
VOLUME ["/app/data", "/app/reports", "/app/docs"]

CMD ["pricewatch", "run", "--send-email"]
