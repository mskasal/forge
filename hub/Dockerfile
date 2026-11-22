FROM python:3.13-slim

WORKDIR /app

# Install only lightweight Hub runtime dependencies (~40 MB RAM; zero Build123d/OCCT)
RUN pip install --no-cache-dir \
    "fastapi>=0.115.0" \
    "uvicorn[standard]>=0.30.0" \
    "python-multipart>=0.0.12" \
    "paho-mqtt>=2.1.0"

COPY app.py preview.html ./
COPY printers ./printers
COPY static ./static

RUN useradd --system --home /var/lib/forge --shell /usr/sbin/nologin forge \
    && mkdir -p /var/lib/forge /etc/forge \
    && chown -R forge:forge /var/lib/forge /app

USER forge
EXPOSE 8590

ENV FORGE_DATA=/var/lib/forge
ENV FORGE_TOKENS=/etc/forge/tokens

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8590"]
