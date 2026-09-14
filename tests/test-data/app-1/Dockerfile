FROM registry.example.com/apps/app-1:2.0

WORKDIR /app

COPY . /app

RUN chmod +x /app/start.sh

EXPOSE 8080

CMD ["./start.sh"]
