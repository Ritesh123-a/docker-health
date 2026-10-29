"""Health checks for Docker containers and the host."""
from dataclasses import dataclass

import docker
import psutil


@dataclass
class Alert:
    key: str        # unique id, used for de-duplication
    severity: str   # "warning" | "critical"
    message: str


def level(value, warn, crit):
    if value >= crit:
        return "critical"
    if value >= warn:
        return "warning"
    return None


def check_host(cfg):
    h, alerts, metrics = cfg["host"], [], {}

    def eval_metric(name, value, thr, label):
        metrics[f"host_{name}"] = value
        sev = level(value, thr["warn"], thr["crit"])
        if sev:
            alerts.append(Alert(f"host:{name}", sev, f"{label} at {value:.1f}"))

    eval_metric("cpu_percent", psutil.cpu_percent(interval=1), h["cpu"], "Host CPU %")
    eval_metric("memory_percent", psutil.virtual_memory().percent, h["memory"], "Host memory %")
    eval_metric("swap_percent", psutil.swap_memory().percent, h["swap"], "Host swap %")

    cores = psutil.cpu_count() or 1
    eval_metric("load_per_core", psutil.getloadavg()[0] / cores, h["load_per_core"], "Load per core")

    for path in h["disk_paths"]:
        try:
            pct = psutil.disk_usage(path).percent
        except OSError as e:
            alerts.append(Alert(f"host:disk:{path}", "warning", f"Cannot read {path}: {e}"))
            continue
        metrics[f"host_disk_percent{{path=\"{path}\"}}"] = pct
        sev = level(pct, h["disk"]["warn"], h["disk"]["crit"])
        if sev:
            alerts.append(Alert(f"host:disk:{path}", sev, f"Disk {path} at {pct:.1f}%"))
    return alerts, metrics


def _container_usage(c):
    s = c.stats(stream=False)
    cpu_d = s["cpu_stats"]["cpu_usage"]["total_usage"] - s["precpu_stats"]["cpu_usage"]["total_usage"]
    sys_d = s["cpu_stats"].get("system_cpu_usage", 0) - s["precpu_stats"].get("system_cpu_usage", 0)
    ncpu = s["cpu_stats"].get("online_cpus") or 1
    cpu = (cpu_d / sys_d) * ncpu * 100 if sys_d > 0 else 0.0
    m = s["memory_stats"]
    used = m.get("usage", 0) - m.get("stats", {}).get("inactive_file", 0)
    limit = m.get("limit") or 0
    mem = used / limit * 100 if limit else 0.0
    return cpu, mem


def check_docker(client, cfg, state):
    cc, alerts, metrics = cfg["containers"], [], {}
    try:
        client.ping()
    except Exception as e:
        return [Alert("docker:daemon", "critical", f"Docker daemon unreachable: {e}")], metrics

    for c in client.containers.list(all=True):
        name = c.name
        if name in cc.get("ignore", []):
            continue
        st = c.attrs["State"]
        status = st["Status"]
        health = st.get("Health", {}).get("Status")
        metrics[f'container_up{{name="{name}"}}'] = 1 if status == "running" else 0

        if st.get("OOMKilled"):
            alerts.append(Alert(f"c:{name}:oom", "critical", f"{name} was OOM-killed"))
        if status in ("exited", "dead") and st.get("ExitCode", 0) != 0:
            alerts.append(Alert(f"c:{name}:down", "critical",
                                f"{name} is {status} (exit code {st['ExitCode']})"))
        if status == "restarting":
            alerts.append(Alert(f"c:{name}:restarting", "critical", f"{name} is restarting"))
        if health == "unhealthy":
            alerts.append(Alert(f"c:{name}:unhealthy", "critical", f"{name} healthcheck failing"))

        rc = c.attrs.get("RestartCount", 0)
        prev = state["restarts"].get(c.id, rc)
        state["restarts"][c.id] = rc
        if rc - prev >= cc["restart_delta"]:
            alerts.append(Alert(f"c:{name}:loop", "critical",
                                f"{name} restart loop ({rc - prev} restarts since last check)"))

        if status == "running":
            try:
                cpu, mem = _container_usage(c)
            except Exception:
                continue
            metrics[f'container_cpu_percent{{name="{name}"}}'] = cpu
            metrics[f'container_mem_percent{{name="{name}"}}'] = mem
            if cpu >= cc["cpu_warn"]:
                alerts.append(Alert(f"c:{name}:cpu", "warning", f"{name} CPU {cpu:.0f}%"))
            if mem >= cc["mem_warn"]:
                alerts.append(Alert(f"c:{name}:mem", "warning", f"{name} memory {mem:.0f}% of limit"))
    return alerts, metrics
