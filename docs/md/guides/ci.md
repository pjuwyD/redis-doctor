# CI integration

`analyze --fail-on critical` returns a non-zero exit code when problems are found,
so it drops straight into a pipeline as a health gate. See the full
[exit-code contract](../output-and-exit-codes.md#exit-codes).

## GitHub Actions

```yaml
- name: Redis health gate
  run: |
    pipx install redis-doctor
    redis-doctor analyze "$REDIS_URL" --fail-on critical
  env:
    REDIS_URL: ${{ secrets.REDIS_URL }}
```

Archive a JSON report as an artifact and compare across runs:

```yaml
- name: Redis report
  run: redis-doctor analyze "$REDIS_URL" --format json --output redis-report.json --no-fail
- uses: actions/upload-artifact@v4
  with:
    name: redis-report
    path: redis-report.json
```

## GitLab CI

```yaml
redis-health:
  image: python:3.11-slim
  script:
    - pip install redis-doctor
    - redis-doctor analyze "$REDIS_URL" --fail-on critical
```

## Kubernetes CronJob

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: redis-doctor
spec:
  schedule: "0 * * * *"
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: Never
          containers:
            - name: redis-doctor
              image: redis-doctor:latest
              args: ["analyze", "redis://my-redis:6379", "--fail-on", "critical"]
```

## Tips

- Use `--fail-on warning` for a stricter gate (exit `1` on warnings, `2` on
  criticals).
- Use `--no-fail` when you only want to capture a report, not gate the build.
- Pass credentials via `REDIS_DOCTOR_PASSWORD` / `REDIS_DOCTOR_USERNAME` rather
  than embedding them in the URL — the password is redacted from output either way
  ([Safety](../safety.md)).
- Disable noisy rules for your environment in a committed `redis-doctor.yml`
  ([Configuration](../configuration.md)).
