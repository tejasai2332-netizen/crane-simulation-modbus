from pymodbus.client import ModbusTcpClient
import time, json
import pandas as pd
from datetime import datetime

# ----------------------------------------------------
# Modbus Connection
# ----------------------------------------------------
client = ModbusTcpClient('127.0.0.1')
if client.connect():
    print("✅ Connected to Modbus server")
else:
    print("❌ Could not connect to Modbus server")

# ----------------------------------------------------
# Modbus Addresses
# ----------------------------------------------------
ADDR = {
    "setX": 1,
    "setY": 2,
    "vacuum": 3,
    "posX": 15,
    "posY": 16,
    "src1_sensor": 17,
    "src2_sensor": 18
}

# Process control and status bits
P1_RUN, P1_RUNNING, P1_SENSOR = 4, 19, 21
P2_RUN, P2_RUNNING, P2_SENSOR = 5, 20, 22

# ----------------------------------------------------
# Constants
# ----------------------------------------------------
SAFE_Y = 200
PICK_Y = 82
TOL = 3
PULSE_MS = 150
PROCESS_TIMEOUT = 20

# ----------------------------------------------------
# Modbus Helpers
# ----------------------------------------------------
def read_value(addr):
    r = client.read_holding_registers(address=addr, count=1)
    return r.registers[0]

def write_value(addr, val):
    client.write_register(addr, val)
    print(f"[WRITE] Address {addr} = {val}")

def pulse(addr, ms=PULSE_MS):
    write_value(addr, 1)
    time.sleep(ms / 1000.0)
    write_value(addr, 0)

# ----------------------------------------------------
# Crane Motion
# ----------------------------------------------------
def wait_until_reached(x_target=None, y_target=None, timeout=8):
    t0 = time.time()
    while time.time() - t0 < timeout:
        x = read_value(ADDR["posX"])
        y = read_value(ADDR["posY"])
        okx = (x_target is None) or (abs(x - x_target) <= TOL)
        oky = (y_target is None) or (abs(y - y_target) <= TOL)
        if okx and oky:
            return True
        time.sleep(0.05)
    print("⚠️ Timeout waiting for crane movement")
    return False

def move_to(x=None, y=None):
    """Safe movement: raise before horizontal travel."""
    if y is not None and y < SAFE_Y:
        write_value(ADDR["setY"], SAFE_Y)
        wait_until_reached(y_target=SAFE_Y)
    if x is not None:
        write_value(ADDR["setX"], x)
        wait_until_reached(x_target=x)
    if y is not None:
        write_value(ADDR["setY"], y)
        wait_until_reached(y_target=y)
    time.sleep(0.1)

def set_vacuum(state):
    write_value(ADDR["vacuum"], state)
    time.sleep(0.2)

# ----------------------------------------------------
# Process Control
# ----------------------------------------------------

def start_process_and_wait(proc: int, timeout=PROCESS_TIMEOUT):
    """Pulse RUN, wait for RUNNING=1→0, and log the actual process time."""
    if proc == 1:
        run_addr, running_addr = P1_RUN, P1_RUNNING
    else:
        run_addr, running_addr = P2_RUN, P2_RUNNING

    print(f"▶ Starting Process {proc}")
    pulse(run_addr)  # send RUN pulse (box starts closing)

    # --- Wait for RUNNING to turn ON (box closing started) ---
    t_start = time.time()
    while time.time() - t_start < timeout:
        if read_value(running_addr) == 1:
            print(f"🔄 Process {proc} RUNNING started")
            t_on = time.time()  # mark start time of RUNNING=1
            break
        time.sleep(0.02)
    else:
        print(f"⚠️ Timeout waiting for Process {proc} to start.")
        return

    # --- Wait for RUNNING to turn OFF (process finished) ---
    while time.time() - t_start < timeout:
        if read_value(running_addr) == 0:
            t_off = time.time()  # mark end time
            duration = t_off - t_on
            print(f"✅ Process {proc} finished after {duration:.2f} seconds.")
            return duration
        time.sleep(0.02)

    print(f"⚠️ Timeout waiting for Process {proc} to finish.")


# ----------------------------------------------------
# Logging (pandas)
# ----------------------------------------------------
log_df = pd.DataFrame(columns=["product_id", "type", "timestamp", "x", "y", "vacuum"])

def log_state(pid, seq_type, vac):
    global log_df
    x = read_value(ADDR["posX"])
    y = read_value(ADDR["posY"])
    t = datetime.now().isoformat(timespec='seconds')
    row = {"product_id": pid, "type": seq_type, "timestamp": t, "x": x, "y": y, "vacuum": vac}
    log_df = pd.concat([log_df, pd.DataFrame([row])], ignore_index=True)
    print(f"[LOG] {row}")

def save_log():
    log_df.to_csv("crane_log.csv", index=False)
    print("📁 Log saved to crane_log.csv")

# ----------------------------------------------------
# Run Sequence from JSON (supports wait_clear & run)
# ----------------------------------------------------
def run_sequence(seq_file, seq_name, pid):
    with open(seq_file) as f:
        data = json.load(f)
    seq = data[seq_name]
    print(f"\n▶ Running sequence: {seq['name']} for product {pid}")

    for step in seq["actions"]:
        vac = read_value(ADDR["vacuum"])

        # --- wait_clear command ---
        if "wait_clear" in step:
            proc = step["wait_clear"]
            running_addr = P1_RUNNING if proc == "P1" else P2_RUNNING
            print(f"⏳ Waiting for {proc} to be clear...")
            while read_value(running_addr) == 1:
                time.sleep(0.1)
            print(f"✅ {proc} clear.")
            continue

        # --- run command ---
        if "run" in step:
            proc = step["run"]
            if proc == "P1":
                start_process_and_wait(proc=1)
            elif proc == "P2":
                start_process_and_wait(proc=2)
            continue

        # --- vacuum control ---
        if "vacuum" in step:
            vac = step["vacuum"]
            set_vacuum(vac)
            log_state(pid, seq_name, vac)

        # --- movement ---
        if "setX" in step or "setY" in step:
            x = step.get("setX", None)
            y = step.get("setY", SAFE_Y)
            move_to(x, y)
            log_state(pid, seq_name, vac)

    print(f"✅ Finished {seq_name} for product {pid}")

# ----------------------------------------------------
# Main Loop
# ----------------------------------------------------
def main():
    pid = 0
    path = r"C:\Users\tejas\OneDrive - Högskolan Väst\Robotics and automation\Sem 1\P 1\PFA\project\Crane simulation\code\crane_sequences.json"
    print("\nCrane ready! Press 'Generate' in the simulation.\n")

    try:
        while True:
            s1 = read_value(ADDR["src1_sensor"])
            s2 = read_value(ADDR["src2_sensor"])

            if s1 == 1:
                pid += 1
                run_sequence(path, "type1", pid)

            if s2 == 1:
                pid += 1
                run_sequence(path, "type2", pid)

            time.sleep(0.3)

    except KeyboardInterrupt:
        print("\n🛑 Program stopped manually.")
    finally:
        save_log()
        client.close()
        print("🔌 Connection closed")

# ----------------------------------------------------
if __name__ == "__main__":
    main()


