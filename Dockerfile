FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# collectstatic runs at start, where settings get their real values from the environment, so the
# non-root user must own STATIC_ROOT.
RUN useradd --create-home --uid 1000 bookit \
    && mkdir /app/staticfiles \
    && chown bookit:bookit /app/staticfiles
USER bookit

EXPOSE 8000

CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py collectstatic --noinput && exec gunicorn BookIt.wsgi:application --bind 0.0.0.0:8000 --workers 3"]
