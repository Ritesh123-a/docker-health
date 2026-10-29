import time
from dataclasses import asdict

import docker
import yaml

import notifier
import server
from checks import check_docker, check_host


def load_config(path="/config/config.yaml"):
    with open(path) as f:
        return yaml.safe_load(f)


def remediate(client, cfg, alerts):
    r = cfg.get("remediation", {})
    for a in alerts:
        if r.get("restart_unhealthy") and a.key.endswith(":unhealthy"):
            name = a.key.split(":")[1]
            try:
                client.containers.get(name).restart()
                notifier.send("warning", f"Auto-restarted {name}")
            except Exception as e:
                notifier.send("critical", f"Auto-restart of {name} failed: {e}")
        if r.get("prune_dangling_on_disk_crit") and a.key.startswith("host:disk") \
                and a.severity == "critical":
            client.images.prune(filters={"dangling": True})
            notifier.send("warning", "Pruned dangling images")


def main():
    cfg = load_config()
    client = docker.from_env()
    state = {"restarts": {}}
    last_sent, active = {}, {}
    server.start()
    notifier.send("warning", "Docker-Health-Guard started")

    while True:
        alerts, metrics = [], {}
        for result in (check_host(cfg), check_docker(client, cfg, state)):
            alerts += result[0]
            metrics.update(result[1])

        server.SNAPSHOT["alerts"] = [asdict(a) for a in alerts]
        server.SNAPSHOT["metrics"] = metrics

        now = time.time()
        current = {a.key: a for a in alerts}
        for key, a in current.items():
            if now - last_sent.get(key, 0) >= cfg["cooldown"]:
                notifier.send(a.severity, a.message)
                last_sent[key] = now
        if cfg.get("send_recovery"):
            for key in set(active) - set(current):
                notifier.send("resolved", f"Cleared: {active[key].message}")
                last_sent.pop(key, None)
        active = current

        remediate(client, cfg, alerts)
        time.sleep(cfg["interval"])


if __name__ == "__main__":
    main()
