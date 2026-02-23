import sys
import re
import os
from collections import Counter

ENTANGLED_PATH_1 = "/proc/sys/kernel/entangled_cpus_1"
ENTANGLED_PATH_2 = "/proc/sys/kernel/entangled_cpus_2"

IGNORE_COMMS = [
            "swapper", "kworker", "migration", "rcu_preempt", "ksoftirqd", 
                "rcu_sched", "cpuhp", "kauditd", "khugepaged", "jbd2", "systemd",
                    "su", "bash", "taskset", "sleep", "sh", "dbus-daemon"
                    ]

def get_current_entanglement():
    try:
        e1, e2 = -1, -1
        if os.path.exists(ENTANGLED_PATH_1):
            with open(ENTANGLED_PATH_1, 'r') as f:
                e1 = int(f.read().strip())
        if os.path.exists(ENTANGLED_PATH_2):
            with open(ENTANGLED_PATH_2, 'r') as f:
                e2 = int(f.read().strip())
        return e1, e2
    except Exception as e:
        return -1, -1


def analyze_trace(filename):
    regex = re.compile(r"\[(\d{3})\]\s+.*?\s+(\d+\.\d+):.*==>\s+next_comm=(.+?)\s+next_pid=(\d+)")

    events = []
    workload_counter = Counter()
    print(f"Reading trace file: {filename}...")

    with open(filename, 'r') as f:
        for line in f:
            if "sched_switch" not in line:
                continue

            m = regex.search(line)
            if m:
                cpu = int(m.group(1))
                time = float(m.group(2))
                comm = m.group(3)
                pid = int(m.group(4))

                is_user = (pid > 0 and not any(comm.startswith(ig) for ig in IGNORE_COMMS))

                if is_user:
                    workload_counter[cpu] += 1

                events.append({'cpu': cpu,'time': time,'comm': comm,'pid': pid,'is_user': is_user})

    k_e1, k_e2 = get_current_entanglement()
    most_common = workload_counter.most_common(2)
    trace_cpus = [c[0] for c in most_common] if most_common else []
    final_e1, final_e2 = -1, -1
    source = "Unknown"

    if len(trace_cpus) == 2:
        final_e1, final_e2 = trace_cpus[0], trace_cpus[1]
        source = "Auto-Detected from Trace (Activity Analysis)"
    elif k_e1 != -1 and k_e2 != -1:
        final_e1, final_e2 = k_e1, k_e2
        source = f"Read from {ENTANGLED_PATH_1}"
    else:
        print("❌ Error: Could not determine entangled CPUs from Kernel or Trace.")
        return

    print(f"✅ Analyzing Entanglement for: CPU {final_e1} and CPU {final_e2}")
    print(f"   (Source: {source})")
    print("-" * 90)
    print(f"{'Time':<15} | {f'CPU {final_e1} Task':<25} | {f'CPU {final_e2} Task':<25} | {'Status'}")
    print("-" * 90)

    state = { final_e1: "idle/sys", final_e2: "idle/sys" }
    violation_count = 0

    for e in events:
        c = e['cpu']
        if c != final_e1 and c != final_e2:
            continue

        task_label = f"{e['comm']} ({e['pid']})" if e['is_user'] else "idle/sys"
        state[c] = task_label

        task1 = state[final_e1]
        task2 = state[final_e2]

        is_busy_1 = task1 != "idle/sys"
        is_busy_2 = task2 != "idle/sys"

        if is_busy_1 and is_busy_2:
            status = "⚠️ VIOLATION"
            violation_count += 1
            print(f"{e['time']:<15.6f} | {task1:<25} | {task2:<25} | {status}")

        elif is_busy_1:
            status = f"✅ CPU {final_e1} Running"
            print(f"{e['time']:<15.6f} | {task1:<25} | {task2:<25} | {status}")
        elif is_busy_2:
            status = f"✅ CPU {final_e2} Running"
            print(f"{e['time']:<15.6f} | {task1:<25} | {task2:<25} | {status}")

    print("-" * 90)
    if violation_count == 0:
        print("SUCCESS: No violations detected")
    else:
        print(f"⚠️ FAILURE: Found {violation_count} instances where both CPUs ran user tasks.")

if __name__ == "__main__":
    target_file = "trace.txt"
    if len(sys.argv) > 1:
        target_file = sys.argv[1]
    analyze_trace(target_file)
