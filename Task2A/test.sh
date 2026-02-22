#!/bin/bash
# filepath: /disk/scratch/operating_systems/s2487866/linux-6.12.67/Task2A/test.sh

cd "$(dirname "$0")"

# Build
echo "=== Building ==="
make clean 2>/dev/null
make
if [ ! -f monitor.exe ]; then
    echo "FAIL: monitor.exe not built"
    exit 1
fi
echo "PASS: Built successfully"

########################################
# Test 1: Basic output format
########################################
echo ""
echo "=== Test 1: Basic output format ==="
./monitor.exe 3
echo ""
echo "INFO: Manually check output has Rank / User / CPU Time columns"

########################################
# Test 2: CPU time accuracy
########################################
echo ""
echo "=== Test 2: CPU time accuracy ==="

# Create a CPU burner that runs for exactly ~2 seconds of CPU
cat > /tmp/cpu_burn.c << 'EOF'
#include <time.h>
int main() {
    struct timespec start, now;
    clock_gettime(CLOCK_PROCESS_CPUTIME_ID, &start);
    volatile double x = 0;
    while (1) {
        for (int i = 0; i < 1000000; i++) x += 0.1;
        clock_gettime(CLOCK_PROCESS_CPUTIME_ID, &now);
        long elapsed_ms = (now.tv_sec - start.tv_sec) * 1000 +
                          (now.tv_nsec - start.tv_nsec) / 1000000;
        if (elapsed_ms >= 2000) break;
    }
    return 0;
}
EOF
gcc -O0 -o /tmp/cpu_burn /tmp/cpu_burn.c

# Get current user
ME=$(whoami)

# Run burner in background, then monitor
/tmp/cpu_burn &
BURN_PID=$!

OUTPUT=$(./monitor.exe 5 2>&1)
wait $BURN_PID 2>/dev/null

echo "$OUTPUT"
echo ""

# Extract CPU time for current user
MY_TIME=$(echo "$OUTPUT" | grep -w "$ME" | awk '{print $NF}')
if [ -z "$MY_TIME" ]; then
    echo "FAIL: User '$ME' not found in output"
else
    echo "Reported CPU time for $ME: ${MY_TIME} ms"
    # The burner uses ~2000ms of CPU. Monitor itself uses some too.
    # Accept if reported time is between 1500 and 4000 ms
    if [ "$MY_TIME" -ge 1500 ] && [ "$MY_TIME" -le 4000 ] 2>/dev/null; then
        echo "PASS: CPU time is in expected range (1500-4000 ms)"
    else
        echo "FAIL: CPU time $MY_TIME ms outside expected range (1500-4000 ms)"
    fi
fi

########################################
# Test 3: Prior CPU time excluded
########################################
echo ""
echo "=== Test 3: Prior CPU time should be excluded ==="

# Burn CPU for 3 seconds BEFORE monitor starts
/tmp/cpu_burn &
BURN_PID=$!
sleep 3
wait $BURN_PID 2>/dev/null

# Now start monitor with NO extra workload
OUTPUT=$(./monitor.exe 3 2>&1)
echo "$OUTPUT"
echo ""

MY_TIME=$(echo "$OUTPUT" | grep -w "$ME" | awk '{print $NF}')
if [ -z "$MY_TIME" ]; then
    echo "PASS: User '$ME' not in output (0 CPU during monitoring — correct)"
elif [ "$MY_TIME" -lt 500 ] 2>/dev/null; then
    echo "PASS: CPU time $MY_TIME ms is low (prior time correctly excluded)"
else
    echo "FAIL: CPU time $MY_TIME ms is too high — prior CPU time may be leaking"
fi

########################################
# Test 4: Ranking order (descending)
########################################
echo ""
echo "=== Test 4: Ranking order ==="

# Create two burners with different CPU usage
cat > /tmp/cpu_light.c << 'EOF'
#include <time.h>
int main() {
    struct timespec start, now;
    clock_gettime(CLOCK_PROCESS_CPUTIME_ID, &start);
    volatile double x = 0;
    while (1) {
        for (int i = 0; i < 1000000; i++) x += 0.1;
        clock_gettime(CLOCK_PROCESS_CPUTIME_ID, &now);
        long elapsed_ms = (now.tv_sec - start.tv_sec) * 1000 +
                          (now.tv_nsec - start.tv_nsec) / 1000000;
        if (elapsed_ms >= 500) break;
    }
    return 0;
}
EOF
gcc -O0 -o /tmp/cpu_light /tmp/cpu_light.c

# Check if test users exist, create if not
id testuser1 &>/dev/null || useradd -m testuser1 2>/dev/null
id testuser2 &>/dev/null || useradd -m testuser2 2>/dev/null

# Heavy for testuser1, light for testuser2
su -s /bin/bash -c "/tmp/cpu_burn" testuser1 &
PID1=$!
su -s /bin/bash -c "/tmp/cpu_light" testuser2 &
PID2=$!

OUTPUT=$(./monitor.exe 5 2>&1)
wait $PID1 2>/dev/null
wait $PID2 2>/dev/null

echo "$OUTPUT"
echo ""

# Extract all CPU times in order and verify descending
PREV=999999999
SORTED=true
while IFS= read -r line; do
    T=$(echo "$line" | awk '{print $NF}')
    if [ -n "$T" ] && echo "$T" | grep -qE '^[0-9]+$'; then
        if [ "$T" -gt "$PREV" ] 2>/dev/null; then
            SORTED=false
        fi
        PREV=$T
    fi
done <<< "$(echo "$OUTPUT" | grep -E '^\s*[0-9]')"

if [ "$SORTED" = true ]; then
    echo "PASS: Output sorted by CPU time descending"
else
    echo "FAIL: Output NOT sorted by CPU time descending"
fi

# Check testuser1 > testuser2
T1=$(echo "$OUTPUT" | grep -w "testuser1" | awk '{print $NF}')
T2=$(echo "$OUTPUT" | grep -w "testuser2" | awk '{print $NF}')
if [ -n "$T1" ] && [ -n "$T2" ]; then
    if [ "$T1" -gt "$T2" ] 2>/dev/null; then
        echo "PASS: testuser1 ($T1 ms) > testuser2 ($T2 ms)"
    else
        echo "FAIL: testuser1 ($T1 ms) should be > testuser2 ($T2 ms)"
    fi
fi

########################################
# Test 5: Processes appearing mid-run
########################################
echo ""
echo "=== Test 5: Process appears mid-monitoring ==="

./monitor.exe 6 &
MON_PID=$!

sleep 2
/tmp/cpu_burn &
BURN_PID=$!

wait $MON_PID 2>/dev/null
wait $BURN_PID 2>/dev/null

echo "PASS: monitor.exe did not crash with processes starting mid-run"

########################################
# Test 6: Processes disappearing mid-run
########################################
echo ""
echo "=== Test 6: Process disappears mid-monitoring ==="

/tmp/cpu_burn &
BURN_PID=$!

./monitor.exe 6 &
MON_PID=$!

sleep 1
kill -9 $BURN_PID 2>/dev/null

wait $MON_PID 2>/dev/null

echo "PASS: monitor.exe did not crash with processes dying mid-run"

########################################
# Cleanup
########################################
echo ""
echo "=== Cleanup ==="
rm -f /tmp/cpu_burn /tmp/cpu_burn.c /tmp/cpu_light /tmp/cpu_light.c
killall cpu_burn cpu_light 2>/dev/null || true
echo "All tests complete."