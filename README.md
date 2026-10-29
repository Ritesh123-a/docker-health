# Docker-Health-Guard

Monitors Docker containers and the host, sends de-duplicated alerts, exposes
`/health` and `/metrics` on port 9100.

## Quick start
1. `cp .env.example .env` and fill in at least one notification channel.
2. Edit `config.yaml` thresholds.
3. `docker compose up -d --build`
4. `docker logs -f docker-health-guard`
5. `curl localhost:9100/health` and `curl localhost:9100/metrics`

## Test it
- `docker run -d --name crashy alpine sh -c "exit 1"` -> critical alert
- `docker run -d --name hog --memory 64m alpine sh -c "tail /dev/zero"` -> OOM alert
- `docker rm -f crashy hog` -> recovery messages

## Prometheus
```yaml
scrape_configs:
  - job_name: docker-health-guard
    static_configs: [{targets: ["host:9100"]}]
```
