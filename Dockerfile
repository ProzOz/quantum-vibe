FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt /app/
RUN apt-get update && apt-get install -y --no-install-recommends \
    graphviz \
    libcurl4 \
    libtk8.6 \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r requirements.txt
COPY . /app
EXPOSE 3000
ENV HOST=0.0.0.0
ENV PORT=3000
CMD ["python", "proxy.py"]
