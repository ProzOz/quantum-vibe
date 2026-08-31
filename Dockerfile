FROM python:3.11-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir qpanda3-runtime pyqpanda3 || echo "qpanda install failed; Origin routes will not work"
EXPOSE 3000
ENV HOST=0.0.0.0
ENV PORT=3000
CMD ["python", "proxy.py"]
