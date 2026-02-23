#!/usr/bin/env python3
# filepath: /disk/scratch/operating_systems/s2487866/linux-6.12.67/analyze_trace.py
"""
Trace Analyzer for OS Coursework 1 - Task 1: Entangled CPUs

Entanglement rule:
  - For a pair of entangled CPUs, they can ONLY run processes belonging
    to the SAME user at any given time.
  - Violation = both CPUs running user tasks from DIFFERENT users simultaneously.
  - Both running tasks from the SAME user = OK
  - One running user task, other idle/kernel = OK
  - Both idle = OK
  - No CPU should be idle for > 10 seconds while runnable tasks exist

Per instructor:
  - Kernel threads are NOT counted as violations (@82)
  - Overlap grading per instance (@52):
    < 5ms    => no loss of marks
    5-100ms  => maybe some marks lost
    > 100ms  => definitely some marks lost
"""

import re
import sys
import os
from collections import defaultdict

class C:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    END = '\033[0m'


# Map comm names to UIDs. Since ftrace doesn't show UID directly,
# we infer from the test structure. The test scripts use taskset to
# pin work/work2 tasks to specific CPUs. We track by comm+pid.
# For a more accurate analysis, we can try to map PIDs to UIDs.

def parse_trace(filepath):
    """Parse trace.txt and extract sched_switch events."""
    events = []
    pattern = re.compile(
        r'^\s*(.+?)-(\d+)\s+\[(\d+)\]\s+\S+\s+'
        r'(\d+\.\d+):\s+sched_switch:\s+'
        r'prev_comm=(.+?)\s+prev_pid=(\d+)\s+prev_prio=(\d+)\s+prev_state=(\S+)\s+'
        r'==>\s+next_comm=(.+?)\s+next_pid=(\d+)\s+next_prio=(\d+)'
    )

    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            m = pattern.match(line)
            if m:
                events.append({
                    'prev_comm': m.group(5).strip(),
                    'prev_pid': int(m.group(6)),
                    'cpu': int(m.group(3)),
                    'timestamp': float(m.group(4)),
                    'next_comm': m.group(9).strip(),
                    'next_pid': int(m.group(10)),
                })

    events.sort(key=lambda e: e['timestamp'])
    return events


def is_kthread(comm, pid):
    """Check if a task is a kernel thread."""
    if pid == 0:
        return True
    kthread_prefixes = [
        "swapper", "kworker", "migration", "rcu_preempt", "ksoftirqd",
        "rcu_sched", "cpuhp", "kauditd", "khugepaged", "jbd2",
        "rcu_par_gp", "kdevtmpfs", "netns", "kcompactd", "writeback",
        "kblockd", "watchdog", "irq_work", "mm_percpu_wq", "ksmd",
        "khungtaskd", "oom_reaper", "kswapd", "kthreadd", "rcu_gp",
        "rcu_bh", "kintegrityd", "ksgxd", "inet_frag_wq", "ext4",
        "acpi", "scsi", "ata", "card0", "i915",
    ]
    for prefix in kthread_prefixes:
        if comm.startswith(prefix):
            return True
    return False


def is_user_task(comm, pid):
    """Check if a task is a user-space task (subject to entanglement)."""
    if pid == 0:
        return False
    return not is_kthread(comm, pid)


def detect_entangled_cpus(events):
    """Auto-detect entangled CPUs based on user task activity."""
    cpu_user_count = defaultdict(int)
    for e in events:
        if is_user_task(e['next_comm'], e['next_pid']):
            cpu_user_count[e['cpu']] += 1
    top_cpus = sorted(cpu_user_count.keys(), key=lambda c: -cpu_user_count[c])
    if len(top_cpus) >= 2:
        return sorted(top_cpus[:2])
    return sorted(set(e['cpu'] for e in events))


def build_cpu_intervals(events, cpu):
    """Build time intervals of what's running on a CPU."""
    cpu_events = [(e['timestamp'], e['next_comm'], e['next_pid'])
                  for e in events if e['cpu'] == cpu]
    cpu_events.sort()

    intervals = []
    for i in range(len(cpu_events) - 1):
        ts, comm, pid = cpu_events[i]
        next_ts = cpu_events[i + 1][0]
        intervals.append({
            'start': ts,
            'end': next_ts,
            'comm': comm,
            'pid': pid,
            'is_user': is_user_task(comm, pid),
            'is_kthread': is_kthread(comm, pid),
            'duration': next_ts - ts,
        })
    return intervals


def get_uid_for_task(comm, pid, uid_map):
    """
    Get UID for a task. Since ftrace doesn't show UID, we use a mapping.
    The test scripts typically run tasks under specific users.
    We try to infer UID from the task name or use the provided uid_map.
    """
    if pid == 0:
        return 0  # kernel

    key = (comm, pid)
    if key in uid_map:
        return uid_map[key]

    # Default: assign UID based on comm name pattern
    # In tests, 'work' and 'work2' are user workload tasks
    # All user tasks without explicit mapping get UID -1 (unknown)
    return -1


def build_uid_map_from_trace(events, cpu_x, cpu_y):
    """
    Try to build a UID map from trace context.
    Since ftrace doesn't give UIDs, we use heuristics:
    - Tasks launched by the same test script (same parent comm) likely share UID
    - For the coursework tests, work/work2 are run by test.XXX.sh scripts
    
    We group tasks by their launcher script to infer same-user relationships.
    """
    uid_map = {}
    # Track which test script launched which tasks on which CPU
    # This is a heuristic - in practice, tasks pinned to the same CPU
    # by the same test script belong to the same user
    
    # For now, we'll use a simple approach: ask the user or use comm names
    # Since the tests use 'work' and 'work2', and the entanglement rule
    # is about same UID, we need to know which PIDs have the same UID.
    
    # Simple heuristic: group by comm name prefix
    # work tasks with different PIDs on different CPUs may be same or different users
    
    return uid_map


def compute_violations(events, cpu_x, cpu_y, uid_map=None):
    """
    Compute violations: intervals where both entangled CPUs run user tasks
    from DIFFERENT users simultaneously.
    
    Both running tasks from the SAME user = OK (entangled correctly)
    Both running tasks from DIFFERENT users = VIOLATION
    One running user task, other idle/kernel = OK  
    Both idle/kernel = OK
    """
    if uid_map is None:
        uid_map = {}
    
    intervals_x = build_cpu_intervals(events, cpu_x)
    intervals_y = build_cpu_intervals(events, cpu_y)

    if not intervals_x or not intervals_y:
        return [], []

    all_times = set()
    for iv in intervals_x + intervals_y:
        all_times.add(iv['start'])
        all_times.add(iv['end'])
    all_times = sorted(all_times)

    def get_state_at(intervals, t):
        for iv in intervals:
            if iv['start'] <= t < iv['end']:
                return iv
        return None

    violations = []      # Different users on both CPUs
    both_user = []       # Both CPUs running user tasks (for info)
    current_violation = None

    for i in range(len(all_times) - 1):
        t_start = all_times[i]
        t_end = all_times[i + 1]
        duration = t_end - t_start

        if duration <= 0:
            continue

        state_x = get_state_at(intervals_x, t_start)
        state_y = get_state_at(intervals_y, t_start)

        if state_x is None or state_y is None:
            if current_violation is not None:
                violations.append(current_violation)
                current_violation = None
            continue

        user_x = state_x['is_user']
        user_y = state_y['is_user']

        # Only check when BOTH CPUs run user tasks
        if user_x and user_y:
            # Check if same user (by UID mapping or comm heuristic)
            uid_x = get_uid_for_task(state_x['comm'], state_x['pid'], uid_map)
            uid_y = get_uid_for_task(state_y['comm'], state_y['pid'], uid_map)
            
            # If UIDs are known and different => violation
            # If UIDs unknown, use comm-based heuristic
            is_same_user = False
            
            if uid_x >= 0 and uid_y >= 0:
                is_same_user = (uid_x == uid_y)
            else:
                # Heuristic: same comm name = likely same user
                # Different comm = likely different user  
                # This is imperfect but works for the test cases
                is_same_user = (state_x['comm'] == state_y['comm'])
            
            both_user.append({
                'start': t_start,
                'end': t_end,
                'duration': duration,
                'cpu_x_comm': state_x['comm'],
                'cpu_x_pid': state_x['pid'],
                'cpu_y_comm': state_y['comm'],
                'cpu_y_pid': state_y['pid'],
                'same_user': is_same_user,
            })
            
            is_violation = not is_same_user
            
            if is_violation:
                if current_violation is None:
                    current_violation = {
                        'start': t_start,
                        'end': t_end,
                        'duration': duration,
                        'cpu_x_comm': state_x['comm'],
                        'cpu_x_pid': state_x['pid'],
                        'cpu_y_comm': state_y['comm'],
                        'cpu_y_pid': state_y['pid'],
                    }
                else:
                    current_violation['end'] = t_end
                    current_violation['duration'] = t_end - current_violation['start']
                    current_violation['cpu_x_comm'] = state_x['comm']
                    current_violation['cpu_x_pid'] = state_x['pid']
                    current_violation['cpu_y_comm'] = state_y['comm']
                    current_violation['cpu_y_pid'] = state_y['pid']
            else:
                if current_violation is not None:
                    violations.append(current_violation)
                    current_violation = None
        else:
            if current_violation is not None:
                violations.append(current_violation)
                current_violation = None

    if current_violation is not None:
        violations.append(current_violation)

    return violations, both_user


def check_idle_timeout(events, cpu_x, cpu_y, max_idle_seconds=10):
    """Check if any entangled CPU was idle for more than max_idle_seconds."""
    violations = []

    for cpu in [cpu_x, cpu_y]:
        intervals = build_cpu_intervals(events, cpu)
        idle_start = None
        idle_end = None
        for iv in intervals:
            if not iv['is_user']:
                if idle_start is None:
                    idle_start = iv['start']
                idle_end = iv['end']
            else:
                if idle_start is not None:
                    idle_duration = idle_end - idle_start
                    if idle_duration > max_idle_seconds:
                        violations.append({
                            'cpu': cpu,
                            'start': idle_start,
                            'end': idle_end,
                            'duration': idle_duration,
                        })
                idle_start = None
                idle_end = None

        if idle_start is not None and idle_end is not None:
            idle_duration = idle_end - idle_start
            if idle_duration > max_idle_seconds:
                violations.append({
                    'cpu': cpu,
                    'start': idle_start,
                    'end': idle_end,
                    'duration': idle_duration,
                })

    return violations


def compute_cpu_time(events, cpu):
    """Compute time per task on a CPU."""
    intervals = build_cpu_intervals(events, cpu)
    cpu_times = defaultdict(float)
    for iv in intervals:
        cpu_times[(iv['comm'], iv['pid'])] += iv['duration']
    return cpu_times


def grade_overlap(duration_ms):
    if duration_ms < 5:
        return 'GOOD', C.GREEN
    elif duration_ms <= 100:
        return 'WARN', C.YELLOW
    else:
        return 'BAD', C.RED


def print_report(events, cpu_x, cpu_y, violations, both_user, idle_violations, 
                 uid_map=None, test_name=""):
    print(f"\n{C.BOLD}{'='*80}{C.END}")
    print(f"{C.BOLD}{C.CYAN}  ENTANGLED CPU TRACE ANALYSIS{C.END}")
    if test_name:
        print(f"{C.BOLD}  Test: {test_name}{C.END}")
    print(f"{C.BOLD}{'='*80}{C.END}")

    duration = events[-1]['timestamp'] - events[0]['timestamp'] if events else 0
    print(f"\n{C.BOLD}  TRACE INFO{C.END}")
    print(f"  {'─'*50}")
    print(f"  Entangled CPUs:    {cpu_x} <-> {cpu_y}")
    print(f"  Total events:      {len(events)}")
    print(f"  Trace duration:    {duration:.3f}s")

    # User task PIDs per CPU
    pids_on_cpu = defaultdict(set)
    for e in events:
        if is_user_task(e['next_comm'], e['next_pid']) and e['cpu'] in (cpu_x, cpu_y):
            pids_on_cpu[e['cpu']].add((e['next_comm'], e['next_pid']))
    print(f"\n  CPU {cpu_x} user tasks: {sorted(pids_on_cpu[cpu_x])}")
    print(f"  CPU {cpu_y} user tasks: {sorted(pids_on_cpu[cpu_y])}")

    # ====== ENTANGLEMENT RULE ======
    print(f"\n{C.BOLD}  ENTANGLEMENT RULE{C.END}")
    print(f"  {'─'*70}")
    print(f"  Rule: Both entangled CPUs must run tasks from the SAME user.")
    print(f"  Violation: Both CPUs running user tasks from DIFFERENT users.")
    print(f"  OK: Both same user | One idle/kernel | Both idle")
    print()

    # Both-user-task periods 
    if both_user:
        same_count = sum(1 for b in both_user if b['same_user'])
        diff_count = sum(1 for b in both_user if not b['same_user'])
        same_time = sum(b['duration'] for b in both_user if b['same_user']) * 1000
        diff_time = sum(b['duration'] for b in both_user if not b['same_user']) * 1000
        
        print(f"  Periods with both CPUs running user tasks:")
        print(f"  {C.GREEN}  Same user:      {same_count} instances, {same_time:.3f} ms total{C.END}")
        print(f"  {C.RED if diff_count else C.GREEN}  Different user: {diff_count} instances, {diff_time:.3f} ms total{C.END}")
    else:
        print(f"  {C.GREEN}  No periods with both CPUs running user tasks simultaneously{C.END}")

    # ====== VIOLATION ANALYSIS (KEY METRIC) ======
    print(f"\n{C.BOLD}  VIOLATION ANALYSIS (different users on entangled CPUs){C.END}")
    print(f"  {'─'*70}")
    print(f"  {C.BOLD}Grading per instance (@52):{C.END}")
    print(f"    {C.GREEN}< 5ms    => no loss of marks{C.END}")
    print(f"    {C.YELLOW}5 - 100ms => maybe some marks lost{C.END}")
    print(f"    {C.RED}> 100ms  => definitely some marks lost{C.END}")
    print()

    if not violations:
        print(f"  {C.GREEN}{C.BOLD}✓ PERFECT - No entanglement violations detected!{C.END}")
        print(f"  {C.GREEN}  CPUs never ran tasks from different users simultaneously.{C.END}")
    else:
        total_ms = sum(v['duration'] for v in violations) * 1000
        max_ms = max(v['duration'] for v in violations) * 1000
        avg_ms = total_ms / len(violations)
        min_ms = min(v['duration'] for v in violations) * 1000

        good_count = sum(1 for v in violations if v['duration'] * 1000 < 5)
        warn_count = sum(1 for v in violations if 5 <= v['duration'] * 1000 <= 100)
        bad_count = sum(1 for v in violations if v['duration'] * 1000 > 100)

        print(f"  Total violations:     {len(violations)}")
        print(f"  Total violation time: {total_ms:.3f} ms")
        print(f"  Average per instance: {avg_ms:.3f} ms")
        print(f"  Min violation:        {min_ms:.3f} ms")
        print(f"  Max violation:        {max_ms:.3f} ms")
        print()
        print(f"  {C.GREEN}  < 5ms instances:    {good_count}{C.END}")
        print(f"  {C.YELLOW}  5-100ms instances:  {warn_count}{C.END}")
        print(f"  {C.RED}  > 100ms instances:  {bad_count}{C.END}")

        print(f"\n  {'#':<4} {'Duration':<12} {'Grade':<8} {'CPU '+str(cpu_x)+' task':<22} {'CPU '+str(cpu_y)+' task':<22}")
        print(f"  {'─'*72}")
        for i, v in enumerate(sorted(violations, key=lambda x: -x['duration'])):
            dur_ms = v['duration'] * 1000
            grade, color = grade_overlap(dur_ms)
            x_info = f"{v['cpu_x_comm']}({v['cpu_x_pid']})"
            y_info = f"{v['cpu_y_comm']}({v['cpu_y_pid']})"
            print(f"  {color}{i+1:<4} {dur_ms:>8.3f} ms  {grade:<8} {x_info:<22} {y_info:<22}{C.END}")
            if i >= 29:
                remaining = len(violations) - 30
                if remaining > 0:
                    print(f"  ... and {remaining} more")
                break

    # ====== IDLE TIMEOUT ======
    print(f"\n{C.BOLD}  IDLE TIMEOUT CHECK (max 10s per @67){C.END}")
    print(f"  {'─'*50}")
    if not idle_violations:
        print(f"  {C.GREEN}✓ No CPU idle for more than 10 seconds{C.END}")
    else:
        for v in idle_violations:
            print(f"  {C.RED}✗ CPU {v['cpu']} idle for {v['duration']:.3f}s "
                  f"({v['start']:.3f} - {v['end']:.3f}){C.END}")

    # ====== VERDICT ======
    print(f"\n{C.BOLD}  VERDICT{C.END}")
    print(f"  {'─'*50}")

    violation_pass = True
    idle_pass = not idle_violations
    max_ms = 0
    bad_count = 0

    if violations:
        max_ms = max(v['duration'] for v in violations) * 1000
        bad_count = sum(1 for v in violations if v['duration'] * 1000 > 100)
        if bad_count > 0:
            violation_pass = False

    if violation_pass and idle_pass:
        if not violations or max_ms < 5:
            print(f"  {C.GREEN}{C.BOLD}✓ PASS - All violations < 5ms, no idle timeouts{C.END}")
        else:
            print(f"  {C.YELLOW}{C.BOLD}⚠ PARTIAL - Some violations 5-100ms, may lose marks{C.END}")
    else:
        reasons = []
        if not violation_pass:
            reasons.append(f"{bad_count} violation(s) > 100ms")
        if not idle_pass:
            reasons.append(f"{len(idle_violations)} idle timeout(s)")
        print(f"  {C.RED}{C.BOLD}✗ FAIL - {', '.join(reasons)}{C.END}")

    # CPU time
    print(f"\n{C.BOLD}  CPU TIME BREAKDOWN{C.END}")
    print(f"  {'─'*60}")
    for cpu in [cpu_x, cpu_y]:
        cpu_times = compute_cpu_time(events, cpu)
        print(f"\n  CPU {cpu}:")
        sorted_times = sorted(cpu_times.items(), key=lambda x: -x[1])
        total_cpu_time = sum(t for _, t in sorted_times)
        for (comm, pid), time_s in sorted_times[:10]:
            pct = (time_s / total_cpu_time * 100) if total_cpu_time > 0 else 0
            is_u = is_user_task(comm, pid)
            color = C.CYAN if is_u else ''
            end = C.END if is_u else ''
            marker = ' [USER]' if is_u else ''
            print(f"    {color}{comm:<16} PID {pid:<6} {time_s:>8.3f}s ({pct:>5.1f}%){marker}{end}")

    # Summary
    total_ms = sum(v['duration'] for v in violations) * 1000 if violations else 0
    max_ms = max(v['duration'] for v in violations) * 1000 if violations else 0

    print(f"\n{C.BOLD}┌{'─'*62}┐{C.END}")
    print(f"{C.BOLD}│  SUMMARY{'':<53}│{C.END}")
    print(f"{C.BOLD}├{'─'*62}┤{C.END}")
    print(f"{C.BOLD}│  Entanglement rule:  Same user on both CPUs{'':<17}│{C.END}")
    print(f"{C.BOLD}│  Violations:         {len(violations):<40}│{C.END}")
    print(f"{C.BOLD}│  Total violation:    {total_ms:<8.3f} ms{'':<31}│{C.END}")
    print(f"{C.BOLD}│  Max single:         {max_ms:<8.3f} ms{'':<31}│{C.END}")
    print(f"{C.BOLD}│  Idle timeouts:      {len(idle_violations):<40}│{C.END}")

    if violation_pass and idle_pass:
        if not violations or max_ms < 5:
            g = f"{C.GREEN}PASS{C.END}"
        else:
            g = f"{C.YELLOW}PARTIAL{C.END}"
    else:
        g = f"{C.RED}FAIL{C.END}"
    print(f"{C.BOLD}│  Grade:              {g}{C.BOLD}{'':<16}│{C.END}")
    print(f"{C.BOLD}└{'─'*62}┘{C.END}")
    print()


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description='Analyze ftrace for CPU entanglement (same-user rule)'
    )
    parser.add_argument('trace_file', nargs='?', default='trace.txt')
    parser.add_argument('--cpu-x', type=int, default=None)
    parser.add_argument('--cpu-y', type=int, default=None)
    parser.add_argument('--test', '-t', default='')
    parser.add_argument('--idle-timeout', type=float, default=10.0)
    parser.add_argument('--batch', '-b', action='store_true')
    parser.add_argument('--uid-map', '-u', default=None,
                       help='JSON file mapping "comm:pid" -> uid')

    args = parser.parse_args()

    # Load UID map if provided
    uid_map = {}
    if args.uid_map:
        import json
        with open(args.uid_map) as f:
            raw = json.load(f)
            for k, v in raw.items():
                comm, pid = k.rsplit(':', 1)
                uid_map[(comm, int(pid))] = int(v)

    if args.batch:
        dirname = os.path.dirname(args.trace_file) or '.'
        trace_files = sorted([
            os.path.join(dirname, f) for f in os.listdir(dirname)
            if 'trace' in f.lower() and f.endswith('.txt')
        ])
        if not trace_files:
            print(f"{C.RED}No trace files found{C.END}")
            sys.exit(1)
        for tf in trace_files:
            print(f"\n{'#'*80}")
            print(f"# {tf}")
            print(f"{'#'*80}")
            events = parse_trace(tf)
            if not events:
                print(f"  {C.YELLOW}No events{C.END}")
                continue
            cpus = detect_entangled_cpus(events)
            if len(cpus) < 2:
                print(f"  {C.YELLOW}Need 2+ CPUs{C.END}")
                continue
            cpu_x, cpu_y = cpus[0], cpus[1]
            violations, both_user = compute_violations(events, cpu_x, cpu_y, uid_map)
            idle_viols = check_idle_timeout(events, cpu_x, cpu_y, args.idle_timeout)
            print_report(events, cpu_x, cpu_y, violations, both_user, idle_viols, uid_map, tf)
        sys.exit(0)

    if not os.path.isfile(args.trace_file):
        print(f"{C.RED}Error: {args.trace_file} not found{C.END}")
        sys.exit(1)

    events = parse_trace(args.trace_file)
    if not events:
        print(f"{C.RED}No sched_switch events found{C.END}")
        sys.exit(1)

    print(f"  Parsed {len(events)} events")

    if args.cpu_x is not None and args.cpu_y is not None:
        cpu_x, cpu_y = args.cpu_x, args.cpu_y
    else:
        cpus = detect_entangled_cpus(events)
        if len(cpus) < 2:
            print(f"{C.RED}Need 2+ CPUs. Use --cpu-x/--cpu-y{C.END}")
            sys.exit(1)
        cpu_x, cpu_y = cpus[0], cpus[1]
        print(f"  Detected entangled CPUs: {cpu_x} and {cpu_y}")

    violations, both_user = compute_violations(events, cpu_x, cpu_y, uid_map)
    idle_viols = check_idle_timeout(events, cpu_x, cpu_y, args.idle_timeout)
    print_report(events, cpu_x, cpu_y, violations, both_user, idle_viols, uid_map, args.test)

    if violations:
        max_ms = max(v['duration'] for v in violations) * 1000
        sys.exit(0 if max_ms < 5 else 1)
    sys.exit(0)


if __name__ == '__main__':
    main()
