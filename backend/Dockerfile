FROM python:3.11

WORKDIR /NCar

COPY . /NCar

RUN pip install --upgrade pip && pip install -r requirements.txt

ENV PYTHONUNBUFFERED=1

CMD ["gunicorn", "backend.wsgi:application", "--bind", "0.0.0.0:8000"]