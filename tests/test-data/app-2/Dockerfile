FROM registry.example.com/apps/app-2:3.0

WORKDIR /opt/application

COPY target/application.jar application.jar

ENV JAVA_OPTS="-Xms256m -Xmx512m"

EXPOSE 8080

ENTRYPOINT ["sh", "-c", "java $JAVA_OPTS -jar application.jar"]
