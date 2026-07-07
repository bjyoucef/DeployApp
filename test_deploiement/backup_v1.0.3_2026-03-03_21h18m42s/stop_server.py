import tkinter as tk
from tkinter import messagebox, ttk
import subprocess
import re
import platform


# ------------------ SYSTEM ------------------
ENCODING = "utf-8"
ERRORS = "ignore"


def get_active_ports():
    """
    Retourne une liste de dictionnaires :
    [{port, pid, process}]
    """
    results = []
    seen = set()

    try:
        if platform.system() == "Windows":
            netstat_cmd = "netstat -ano"
            tasklist_cmd_template = 'tasklist /FI "PID eq {}"'
        else:  # Linux/Mac
            netstat_cmd = "netstat -tuln"
            tasklist_cmd_template = "ps -p {} -o comm="

        netstat_output = subprocess.check_output(
            netstat_cmd,
            shell=True,
            encoding=ENCODING,
            errors=ERRORS
        )

        for line in netstat_output.splitlines():
            if "LISTEN" not in line and "LISTENING" not in line:
                continue

            parts = re.split(r"\s+", line.strip())
            if len(parts) < 4:
                continue

            # Extraction du port selon l'OS
            if platform.system() == "Windows":
                local_address = parts[1]
                pid = parts[-1]
            else:  # Linux/Mac
                local_address = parts[3]
                pid = parts[6] if len(parts) > 6 else "N/A"

            if ":" not in local_address:
                continue

            port = local_address.split(":")[-1]
            key = (port, pid)
            if key in seen:
                continue
            seen.add(key)

            # Récupérer le nom du processus
            try:
                if platform.system() == "Windows":
                    tasklist_output = subprocess.check_output(
                        tasklist_cmd_template.format(pid),
                        shell=True,
                        encoding=ENCODING,
                        errors=ERRORS
                    )
                    lines = tasklist_output.splitlines()
                    process_name = lines[3].split()[0] if len(lines) > 3 else "Inconnu"
                else:
                    try:
                        process_name = subprocess.check_output(
                            tasklist_cmd_template.format(pid),
                            shell=True,
                            encoding=ENCODING,
                            errors=ERRORS
                        ).strip() or "Inconnu"
                    except:
                        process_name = "Inconnu"
            except:
                process_name = "Inconnu"

            results.append({
                "port": port,
                "pid": pid,
                "process": process_name
            })

    except Exception as e:
        messagebox.showerror("Erreur système", str(e))

    return results


# ------------------ UI ACTIONS ------------------
def refresh():
    """Rafraîchit la liste des ports avec recherche appliquée"""
    global all_processes
    all_processes = get_active_ports()
    apply_search()


def apply_search():
    """Applique le filtre de recherche sur la liste des processus"""
    search_term = search_var.get().lower()
    filtered = []

    for item in all_processes:
        if (search_term in item['port'].lower() or
            search_term in item['pid'].lower() or
            search_term in item['process'].lower()):
            filtered.append(item)

    display_processes(filtered)


def display_processes(processes_list):
    """Affiche les processus dans le tableau"""
    tree.delete(*tree.get_children())
    processes.clear()

    for item in processes_list:
        tree.insert(
            "",
            "end",
            values=("☐", item['port'], item['pid'], item['process'])
        )
        processes.append(item)



def toggle_selection(event):
    region = tree.identify_region(event.x, event.y)
    if region != "cell":
        return

    row = tree.identify_row(event.y)
    col = tree.identify_column(event.x)

    if col == "#1" and row:
        current = tree.set(row, "select")
        tree.set(row, "select", "✔" if current == "☐" else "☐")



def stop_selected():
    """Arrête les processus sélectionnés"""
    selected = []

    if not selected:
        messagebox.showwarning("Aucune sélection", "Aucun processus sélectionné.")
        return

    if not messagebox.askyesno(
        "Confirmation",
        f"Arrêter {len(selected)} processus sélectionné(s) ?\n"
        "Cette action est irréversible !"
    ):
        return
    for row_id in tree.get_children():
        if tree.set(row_id, "select") == "✔":
            idx = tree.index(row_id)
            selected.append(processes[idx])



def toggle_all():
    all_checked = all(tree.set(r, "select") == "✔" for r in tree.get_children())
    for r in tree.get_children():
        tree.set(r, "select", "☐" if all_checked else "✔")


def on_tree_select(event):
    """Met à jour la sélection lors du clic sur les checkboxes"""
    for i, item in enumerate(tree.get_children()):
        check_vars[i].set(tree.item(item, "values")[-1] == "✔")


# ------------------ TKINTER UI ------------------
root = tk.Tk()
root.title("Gestionnaire de Ports Réseau")
root.geometry("850x550")
root.minsize(800, 500)
root.configure(bg="#f5f6f7")

# Variables globales
check_vars = []
processes = []
all_processes = []
search_var = tk.StringVar()

# Style moderne
style = ttk.Style()
style.theme_use("clam")

# Configuration des couleurs
PRIMARY_COLOR = "#4361ee"
SECONDARY_COLOR = "#3f37c9"
SUCCESS_COLOR = "#4cc9f0"
DANGER_COLOR = "#f72585"
WARNING_COLOR = "#f8961e"
LIGHT_BG = "#f8f9fa"
DARK_TEXT = "#212529"
LIGHT_TEXT = "#f8f9fa"

# Style du Treeview
style.configure("Treeview",
                background=LIGHT_BG,
                foreground=DARK_TEXT,
                rowheight=30,
                fieldbackground=LIGHT_BG,
                font=("Segoe UI", 10))
style.configure("Treeview.Heading",
                background=PRIMARY_COLOR,
                foreground=LIGHT_TEXT,
                font=("Segoe UI Semibold", 10),
                padding=5)
style.map("Treeview",
          background=[('selected', SECONDARY_COLOR)],
          foreground=[('selected', LIGHT_TEXT)])
style.map("Treeview.Heading",
          background=[('active', SECONDARY_COLOR)])

# Barre de recherche et contrôles
control_frame = tk.Frame(root, bg="#f5f6f7", pady=10, padx=15)
control_frame.pack(fill="x")

# Zone de recherche
search_frame = tk.Frame(control_frame, bg="#f5f6f7")
search_frame.pack(side="left", fill="x", expand=True, padx=(0, 10))

tk.Label(search_frame, text="🔍", bg="#f5f6f7", font=("Segoe UI", 12), fg="#6c757d").pack(side="left", padx=(0, 5))
search_entry = tk.Entry(
    search_frame,
    textvariable=search_var,
    font=("Segoe UI", 11),
    relief="solid",
    borderwidth=1,
    highlightthickness=0,
    width=40
)
search_entry.pack(side="left", fill="x", expand=True, ipady=4)
search_entry.bind("<KeyRelease>", lambda e: apply_search())

# Boutons de contrôle
button_frame = tk.Frame(control_frame, bg="#f5f6f7")
button_frame.pack(side="right")

toggle_btn = tk.Button(
    button_frame,
    text="☑ Tout sélectionner",
    command=toggle_all,
    font=("Segoe UI", 10),
    bg=WARNING_COLOR,
    fg="white",
    relief="flat",
    padx=15,
    pady=5,
    cursor="hand2"
)
toggle_btn.pack(side="left", padx=5)

refresh_btn = tk.Button(
    button_frame,
    text="🔄 Rafraîchir",
    command=refresh,
    font=("Segoe UI", 10),
    bg=SUCCESS_COLOR,
    fg="white",
    relief="flat",
    padx=15,
    pady=5,
    cursor="hand2"
)
refresh_btn.pack(side="left", padx=5)

stop_btn = tk.Button(
    button_frame,
    text="🛑 Arrêter sélection",
    command=stop_selected,
    font=("Segoe UI Semibold", 10),
    bg=DANGER_COLOR,
    fg="white",
    relief="flat",
    padx=15,
    pady=5,
    cursor="hand2"
)
stop_btn.pack(side="left", padx=5)

# Tableau des processus
tree_frame = tk.Frame(root, bg=LIGHT_BG, padx=10, pady=5)
tree_frame.pack(fill="both", expand=True, padx=15, pady=(0, 15))

# Scrollbars
tree_scroll_y = ttk.Scrollbar(tree_frame)
tree_scroll_y.pack(side="right", fill="y")

tree_scroll_x = ttk.Scrollbar(tree_frame, orient="horizontal")
tree_scroll_x.pack(side="bottom", fill="x")

# Création du Treeview
tree = ttk.Treeview(
    tree_frame,
    columns=("select", "port", "pid", "process"),
    show="headings",
    yscrollcommand=tree_scroll_y.set,
    xscrollcommand=tree_scroll_x.set
        )

tree_scroll_y.config(command=tree.yview)
tree_scroll_x.config(command=tree.xview)

# Configuration des colonnes
tree.heading("select", text="✔")
tree.heading("port", text="Port")
tree.heading("pid", text="PID")
tree.heading("process", text="Processus")

tree.column("select", width=40, anchor="center")
tree.column("port", width=100, anchor="center")
tree.column("pid", width=100, anchor="center")
tree.column("process", width=350, anchor="w")

# Ajout des checkboxes virtuelles
tree.pack(fill="both", expand=True)

# Ajout des tags pour le style des lignes
tree.tag_configure("evenrow", background="#f8f9fa")
tree.tag_configure("oddrow", background="#e9ecef")
tree.tag_configure("selected", background=SECONDARY_COLOR, foreground="white")

# Binding des événements
tree.bind("<Button-1>", toggle_selection)

# Initialisation des données
refresh()

# Footer
footer = tk.Frame(root, bg="#e9ecef", height=30)
footer.pack(fill="x", side="bottom")
tk.Label(
    footer,
    text=f"Port Manager Pro • {platform.system()} {platform.release()} • Développé avec ❤️",
    bg="#e9ecef",
    fg="#6c757d",
    font=("Segoe UI", 8)
).pack(pady=5)

root.mainloop()