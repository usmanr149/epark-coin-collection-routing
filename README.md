Start a redis docker container called redis

docker run --name redis -d redis

Compose the docker container with this command

docker build -t parkingservices .

Run uwsgi-nginx-flask web app with this command

docker run -p 80:80 --link redis parkingservices

The web app will run on port 80.