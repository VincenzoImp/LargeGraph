"""Run an experiment in a rootless systemd cgroup with measured hard limits."""

from __future__ import annotations

import argparse
import contextlib
import json
import shutil
import subprocess
import time
import uuid
from pathlib import Path

from .runtime import environment, write_json


def run_constrained(command, output: Path, memory_gb=8.0, cpu_cores=8.0, cwd: Path | None = None):
    if memory_gb <= 0 or cpu_cores <= 0 or not command:
        raise ValueError("A command and positive memory/CPU limits are required")
    cwd = (cwd or Path.cwd()).resolve()
    executable = shutil.which(command[0])
    if executable is None:
        executable = str((cwd / command[0]).resolve())
    command = [executable, *command[1:]]
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    unit = "largegraph-" + uuid.uuid4().hex[:12] + ".service"
    limit = int(memory_gb * 1_000_000_000)
    launch = [
        "systemd-run",
        "--user",
        f"--unit={unit}",
        "--wait",
        "--pipe",
        f"--property=WorkingDirectory={cwd}",
        f"--property=MemoryMax={limit}",
        "--property=MemorySwapMax=0",
        "--property=MemoryAccounting=yes",
        f"--property=CPUQuota={cpu_cores * 100:g}%",
        "--",
        *command,
    ]
    start = time.perf_counter()
    peak = swap_peak = samples = 0
    observed_limits = None
    cgroup = None
    last_events = {}
    write_json(
        output / "launch.json",
        {
            "unit": unit,
            "command": launch,
            "memory_limit_bytes": limit,
            "cpu_quota_cores": cpu_cores,
            "swap_limit_bytes": 0,
            "environment": environment(),
        },
    )
    with (output / "process.log").open("w") as log, (output / "memory.jsonl").open("w") as trace:
        process = subprocess.Popen(launch, stdout=log, stderr=subprocess.STDOUT)
        try:
            while process.poll() is None:
                if cgroup is None:
                    query = subprocess.run(
                        ["systemctl", "--user", "show", unit, "--property=ControlGroup", "--value"],
                        capture_output=True,
                        text=True,
                    )
                    if query.returncode == 0 and query.stdout.strip():
                        cgroup = Path("/sys/fs/cgroup") / query.stdout.strip().lstrip("/")
                if cgroup is not None:
                    with contextlib.suppress(FileNotFoundError):
                        current = int((cgroup / "memory.current").read_text())
                        peak = max(peak, int((cgroup / "memory.peak").read_text()))
                        swap_peak = max(
                            swap_peak, int((cgroup / "memory.swap.current").read_text())
                        )
                        observed_limits = {
                            "memory_max": (cgroup / "memory.max").read_text().strip(),
                            "memory_swap_max": (cgroup / "memory.swap.max").read_text().strip(),
                            "cpu_max": (cgroup / "cpu.max").read_text().strip(),
                        }
                        last_events = dict(
                            line.split()
                            for line in (cgroup / "memory.events").read_text().splitlines()
                        )
                        trace.write(
                            json.dumps(
                                {
                                    "seconds": time.perf_counter() - start,
                                    "memory_current_bytes": current,
                                    "memory_peak_bytes": peak,
                                    "swap_current_bytes": swap_peak,
                                }
                            )
                            + "\n"
                        )
                        trace.flush()
                        samples += 1
                time.sleep(0.2)
        except BaseException:
            subprocess.run(["systemctl", "--user", "stop", unit], check=False)
            process.wait()
            raise
        returncode = process.wait()
    verified = bool(
        observed_limits
        and observed_limits["memory_max"] == str(limit)
        and observed_limits["memory_swap_max"] == "0"
    )
    if observed_limits:
        quota, period = observed_limits["cpu_max"].split()
        verified = verified and quota != "max" and int(quota) / int(period) <= cpu_cores + 1e-6
    report = {
        "command": command,
        "unit": unit,
        "exit_code": returncode,
        "wall_seconds": time.perf_counter() - start,
        "samples": samples,
        "cgroup_memory_peak_bytes": peak,
        "sampled_swap_peak_bytes": swap_peak,
        "observed_limits": observed_limits,
        "memory_events": last_events,
        "verified_hard_limits": verified,
        "interpretation": "Cgroup memory includes page cache and child processes. CPU quota limits CPU time, not CPU model or physical frequency.",
    }
    write_json(output / "report.json", report)
    if returncode or not verified:
        raise RuntimeError(
            f"Constrained run failed or limits could not be verified; inspect {output}"
        )
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--memory-gb", type=float, default=8)
    parser.add_argument("--cpu-cores", type=float, default=8)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    run_constrained(command, args.output, args.memory_gb, args.cpu_cores)


if __name__ == "__main__":
    main()
