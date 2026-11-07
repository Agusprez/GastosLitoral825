# Imagen de Cuentas Claras para cualquier host con contenedores
# (Render, Fly.io, Railway, Google Cloud Run, tu propio VPS).
#
# La app es sin estado: la base de datos vive en Google Sheets y los comprobantes
# en imgbb o Drive, así que no hace falta volumen persistente. Si usás
# `almacen = "sqlite"` o comprobantes en disco, montá un volumen en /app/data y
# guardá también /app/data/clave.key.

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    CUENTASCLARAS_ALMACEN=sheets

# Dependencias de sistema para Pillow/matplotlib.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libjpeg62-turbo zlib1g libfreetype6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY . .
RUN mkdir -p data

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=3).status == 200 else 1)"

# Los secretos se pasan por variables de entorno CUENTASCLARAS_* (recomendado:
# `CUENTASCLARAS_GCP_CREDENCIALES` con el JSON de la service account en una línea,
# `CUENTASCLARAS_HOJA_URL` y `CUENTASCLARAS_CLAVE_CIFRADO`) o montando
# .streamlit/secrets.toml en /app/.streamlit/secrets.toml.
CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--server.enableXsrfProtection=true", \
     "--browser.gatherUsageStats=false"]
