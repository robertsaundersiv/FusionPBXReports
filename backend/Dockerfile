FROM python:3.12-slim

WORKDIR /app

ARG INSTALL_DEV=false

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt requirements-dev.txt* ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt && \
        if [ "$INSTALL_DEV" = "true" ] && [ -f requirements-dev.txt ]; then \
            pip install --no-cache-dir -r requirements-dev.txt; \
        fi

# Copy application
COPY . .

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
