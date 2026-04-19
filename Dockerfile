FROM python:3.12-slim

LABEL maintainer="viibeware Corp. <hello@viibeware.dev>"
LABEL description="viibeware Corp. corporate website"

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Copy application code
COPY app.py .
COPY CHANGELOG.md .
COPY templates/ templates/
COPY static/ static/
COPY data/content.example.json data/content.example.json

# Create data directory for persistent content
RUN mkdir -p /app/data

# Default environment variables
# SECRET_KEY, ADMIN_USER, ADMIN_PASS must be provided at runtime (e.g. via --env or compose)
ENV GUNICORN_WORKERS="2"
ENV GUNICORN_PORT="8899"

EXPOSE 8899

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=5s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8899/')" || exit 1

# Run with gunicorn
CMD gunicorn \
  --workers ${GUNICORN_WORKERS} \
  --bind 0.0.0.0:${GUNICORN_PORT} \
  --access-logfile - \
  --error-logfile - \
  app:app
