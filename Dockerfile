# Multi-stage build for redis-doctor.
FROM python:3.11-slim AS build

WORKDIR /src
COPY pyproject.toml README.md ./
COPY redis_doctor ./redis_doctor
COPY rules ./rules

RUN pip install --no-cache-dir build hatchling \
    && pip wheel --no-cache-dir --no-deps -w /wheels .

FROM python:3.11-slim AS runtime

# Create an unprivileged user.
RUN useradd --create-home --uid 10001 doctor
WORKDIR /home/doctor

COPY --from=build /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl \
    && rm -rf /wheels

USER doctor
ENTRYPOINT ["redis-doctor"]
CMD ["--help"]
