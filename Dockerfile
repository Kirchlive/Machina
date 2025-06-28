# LLM2LLM-Bridge Docker Image
# Optimiert für Produktion mit Multi-Stage Build

# Stage 1: Build-Umgebung
FROM python:3.11-slim as builder

# Arbeitsverzeichnis
WORKDIR /app

# System-Abhängigkeiten für Python-Pakete
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Python-Abhängigkeiten installieren
COPY requirements.txt pyproject.toml ./
RUN pip install --user --no-cache-dir -r requirements.txt

# Stage 2: Produktions-Image
FROM python:3.11-slim

# Sicherheits-Updates
RUN apt-get update && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/*

# Nicht-root Benutzer erstellen
RUN useradd -m -u 1000 llmbridge

WORKDIR /app

# Python-Pakete vom Builder kopieren
COPY --from=builder /root/.local /home/llmbridge/.local

# Anwendungscode kopieren
COPY --chown=llmbridge:llmbridge app.core/ ./app.core/
COPY --chown=llmbridge:llmbridge app.api/ ./app.api/
COPY --chown=llmbridge:llmbridge workflows/ ./workflows/
COPY --chown=llmbridge:llmbridge models.yaml ./

# Erstelle Verzeichnisse für Logs und temporäre Dateien
RUN mkdir -p /app/logs /app/temp && \
    chown -R llmbridge:llmbridge /app

# Wechsel zum nicht-root Benutzer
USER llmbridge

# PATH aktualisieren
ENV PATH=/home/llmbridge/.local/bin:$PATH

# Gesundheitscheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/').raise_for_status()"

# Port exponieren
EXPOSE 8000

# Umgebungsvariablen
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Start-Befehl
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]