FROM python:3.7-slim
WORKDIR /app

COPY ./setup.py /app/setup.py
COPY ./README.md /app/README.md
RUN pip install -e ".[dev]"
COPY ./main.py /app/main.py

ENTRYPOINT ["python", "main.py"]
CMD []
