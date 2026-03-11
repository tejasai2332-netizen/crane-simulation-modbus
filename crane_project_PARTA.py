import tkinter as tk
from tkinter import ttk, messagebox
import pandas as pd, json, time
from pymodbus.client import ModbusTcpClient

# ------------------------------------------------------------
# 1. Modbus setup (auto connect with retry)
# ------------------------------------------------------------
client = ModbusTcpClient("127.0.0.1", port=502)

def read_holding(addr):
    res = client.read_holding_registers(address=addr, count=1)
    return None if res.isError() else res.registers[0]

def write_register(addr, val):
    res = client.write_register(address=addr, value=int(val))
    if res.isError():
        print(f" Write failed at {addr}")

def wait_until(addr, target, timeout=5):
    start = time.time()
    while True:
        pos = read_holding(addr)
        if pos == target:
            break
        if time.time() - start > timeout:
            break
        time.sleep(0.05)
        root.update()

def connect_to_simulation():
    print("🔌 Connecting to CraneSimulation...")
    while True:
        if not client.connect():
            print("⏳ Waiting for simulator to start...")
            time.sleep(1)
            continue
        x = read_holding(15)
        y = read_holding(16)
        if x is not None and y is not None:
            print("✅ Connected to CraneSimulation")
            break
        client.close()
        time.sleep(1)

connect_to_simulation()

# ------------------------------------------------------------
# 2. Crane movement
# ------------------------------------------------------------
STEP = 5

def update_position():
    x = read_holding(15)
    y = read_holding(16)
    if x is not None and y is not None:
        x_var.set(x)
        y_var.set(y)
        pos_label.config(text=f"X: {x}   Y: {y}")
    root.after(400, update_position)

def move(dx, dy):
    curx = read_holding(15)
    cury = read_holding(16)
    if curx is None or cury is None:
        messagebox.showwarning("Crane", "Cannot read crane position.")
        return

    newx = curx + dx
    newy = cury + dy

    if dx != 0:
        write_register(1, newx)
        wait_until(15, newx)
    if dy != 0:
        write_register(2, newy)
        wait_until(16, newy)

    x_var.set(newx)
    y_var.set(newy)
    pos_label.config(text=f"X: {newx}   Y: {newy}")

def move_up():    move(0, STEP)
def move_down():  move(0, -STEP)
def move_left():  move(-STEP, 0)
def move_right(): move(STEP, 0)

# ------------------------------------------------------------
# 3. Save / Export Positions
# ------------------------------------------------------------
positions = pd.DataFrame(columns=["setX", "setY"])

def save_position():
    x, y = x_var.get(), y_var.get()
    positions.loc[len(positions)] = [x, y]
    refresh_list()

def refresh_list():
    for w in inner_frame.winfo_children():
        w.destroy()
    for i, row in positions.iterrows():
        ttk.Label(inner_frame, text=f"{i+1}. X={row['setX']}  Y={row['setY']}")\
            .pack(anchor="w", pady=1)
    canvas.update_idletasks()
    canvas.configure(scrollregion=canvas.bbox("all"))

def export_json():
    if positions.empty:
        messagebox.showinfo("Save", "No positions to save.")
        return
    data = {"actions": positions.to_dict(orient="records")}
    with open("crane_positions.json", "w") as f:
        json.dump(data, f, indent=2)
    messagebox.showinfo("Saved", "Positions exported to crane_positions.json")

def clear_positions():
    global positions
    positions = pd.DataFrame(columns=["setX", "setY"])
    refresh_list()

# ------------------------------------------------------------
# 4. GUI Layout (compact scroll list)
# ------------------------------------------------------------
root = tk.Tk()
root.title("Crane HMI – Auto Connect (Compact)")
root.geometry("260x360")
root.resizable(False, False)

x_var = tk.IntVar()
y_var = tk.IntVar()

pos_label = ttk.Label(root, text="X: 0   Y: 0", font=("Arial", 12))
pos_label.pack(pady=5)

frame_arrows = ttk.Frame(root)
frame_arrows.pack(pady=5)
ttk.Button(frame_arrows, text="↑", width=4, command=move_up).grid(row=0, column=1)
ttk.Button(frame_arrows, text="←", width=4, command=move_left).grid(row=1, column=0)
ttk.Button(frame_arrows, text="→", width=4, command=move_right).grid(row=1, column=2)
ttk.Button(frame_arrows, text="↓", width=4, command=move_down).grid(row=2, column=1)

ttk.Button(root, text="Save Current Position", command=save_position).pack(pady=4)

# --- Scrollable saved list (reduced height) ---
frame_container = ttk.Frame(root)
frame_container.pack(fill="both", expand=True, pady=5)

canvas = tk.Canvas(frame_container, height=70)  # 🔹 reduced height from 120 → 70
scrollbar = ttk.Scrollbar(frame_container, orient="vertical", command=canvas.yview)
inner_frame = ttk.Frame(canvas)

def update_scroll_region(event):
    canvas.configure(scrollregion=canvas.bbox("all"))

inner_frame.bind("<Configure>", update_scroll_region)
canvas.create_window((0, 0), window=inner_frame, anchor="nw")
canvas.configure(yscrollcommand=scrollbar.set)

canvas.pack(side="left", fill="both", expand=True)
scrollbar.pack(side="right", fill="y")

ttk.Button(root, text="Export to JSON", command=export_json).pack(pady=4)
ttk.Button(root, text="Clear Positions", command=clear_positions).pack(pady=2)

def on_close():
    client.close()
    print("🔒 Connection closed.")
    root.destroy()

root.protocol("WM_DELETE_WINDOW", on_close)

update_position()
root.mainloop()

