# Verwende ein Basis-Image für Python
FROM python:3.9

# Arbeitsverzeichnis im Container setzen
WORKDIR /app

# Kopiere das Python-Skript und die requirements.txt ins Arbeitsverzeichnis
COPY kab_karte_stable.py .
COPY requirements.txt .

# Installiere die Abhängigkeiten
RUN pip install -r requirements.txt

# Führe das Python-Skript aus, wenn der Container startet
CMD ["streamlit", "run", "kab_karte_stable.py", "--server.port=8501", "--server.address=0.0.0.0"]
