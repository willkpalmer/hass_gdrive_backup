ARG BUILD_FROM
FROM $BUILD_FROM

WORKDIR /app
COPY requirements-addon.txt addon_deps.sh /app/
RUN sh ./addon_deps.sh
COPY . /app

EXPOSE 1627
EXPOSE 8099
ENTRYPOINT ["python3", "-m", "backup"]
