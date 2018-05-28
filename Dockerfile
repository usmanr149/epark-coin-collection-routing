FROM tiangolo/uwsgi-nginx:python3.5

ENV NGINX_WORKER_PROCESSES auto

RUN pip3.5 install flask

# By default, allow unlimited file sizes, modify it to limit the file sizes
# To have a maximum of 1 MB (Nginx's default) change the line to:
ENV NGINX_MAX_UPLOAD 1m
# ENV NGINX_MAX_UPLOAD 0

# By default, Nginx listens on port 80.
# To modify this, change LISTEN_PORT environment variable.
# (in a Dockerfile or with an option for `docker run`)
ENV LISTEN_PORT 80

# Which uWSGI .ini file should be used, to make it customizable
ENV UWSGI_INI /app/uwsgi.ini

# URL under which static (not modified by Python) files will be requested
# They will be served by Nginx directly, without being handled by uWSGI
ENV STATIC_URL /static
# Absolute path in where the static files wil be
ENV STATIC_PATH /app/static

# If STATIC_INDEX is 1, serve / with /static/index.html directly (or the static URL configured)
# ENV STATIC_INDEX 1
ENV STATIC_INDEX 0

# Make /app/* available to be imported by Python globally to better support several use cases like Alembic migrations.
ENV PYTHONPATH=/app

RUN apt-get update -y

RUN apt-get install -y build-essential xvfb less

RUN apt-get install -y python-dev

RUN apt-get install -y libpq-dev libxml2-dev libxslt1-dev libssl-dev libffi-dev

WORKDIR /app

RUN wget https://github.com/wkhtmltopdf/wkhtmltopdf/releases/download/0.12.4/wkhtmltox-0.12.4_linux-generic-amd64.tar.xz
RUN tar -xvf wkhtmltox-0.12.4_linux-generic-amd64.tar.xz
RUN rm wkhtmltox-0.12.4_linux-generic-amd64.tar.xz
WORKDIR /app/wkhtmltox/bin
RUN mv wkhtmltopdf  /usr/bin/wkhtmltopdf

WORKDIR /app

RUN wget http://www.math.uwaterloo.ca/tsp/concorde/downloads/codes/src/co031219.tgz
RUN gunzip co031219.tgz
RUN tar xvf co031219.tar
RUN rm co031219.tar
RUN mkdir QS
WORKDIR /app/concorde/QS
RUN wget http://www.math.uwaterloo.ca/~bico/qsopt/beta/codes/PIC/qsopt.PIC.a
RUN mv qsopt.PIC.a qsopt.a
RUN wget http://www.math.uwaterloo.ca/~bico/qsopt/beta/codes/PIC/qsopt.h
WORKDIR /app/concorde
RUN ./configure --with-qsopt=/app/concorde/QS
WORKDIR /app/concorde
RUN make

WORKDIR /app
# We copy just the requirements.txt first to leverage Docker cache
COPY ./requirements.txt /app/requirements.txt
RUN pip install -r requirements.txt

# Add demo app
COPY . /app
WORKDIR /app

# Copy start.sh script that will check for a /app/prestart.sh script and run it before starting the app
COPY start.sh /start.sh
RUN chmod +x /start.sh

# Copy the entrypoint that will generate Nginx additional configs
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]

WORKDIR /app

# Run the start script, it will check for an /app/prestart.sh script (e.g. for migrations)
# And then will start Supervisor, which in turn will start Nginx and uWSGI
CMD ["/start.sh"]