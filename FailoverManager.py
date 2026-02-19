import socket
import subprocess
import time
import sys
import os

# --- CONFIGURACIÓN ---
AZURE_IP = "20.120.242.3"  # IP PÚBLICA DE AZURE
AZURE_PORT = 5050         # Puerto del servicio
KEY_FILE = "squareroot.pem" 
USER = "azureuser"

# Archivos locales
LOCAL_SERVER = "Server.py"
LOCAL_GATEWAY = "HTTPGateway.py"
LOG_FILE = "PRIMARYAudit.log"

# Variables de estado
local_process_server = None
local_process_gateway = None
failover_active = False

def download_logs():
    """Descarga los votos de Azure usando SCP"""
    print(f"[SYNC] Trayendo votos...", end="")
    try:
        # Comando SCP para traer el log
        cmd = [
            "scp", "-i", KEY_FILE,
            "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=5",
            f"{USER}@{AZURE_IP}:/home/{USER}/voting/{LOG_FILE}",
            "."
        ]
        # Ejecutamos scp ocultando la salida técnica
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(" ✅ OK")
        return True
    except subprocess.CalledProcessError:
        print(" ⚠️ Error copiando archivo")
        return False

def check_azure_via_ssh():
    """
    Truco para saltar el Firewall:
    En lugar de conectar al puerto 5050 (que está bloqueado),
    verificamos si el servidor responde comandos SSH básicos.
    """
    try:
        # Intentamos ejecutar un comando simple 'exit' en el servidor remoto
        cmd = [
            "ssh", "-i", KEY_FILE,
            "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=3", # Si tarda más de 3s, asumimos caído
            f"{USER}@{AZURE_IP}",
            "exit"
        ]
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return result.returncode == 0
    except Exception:
        return False

def activate_failover():
    global local_process_server, local_process_gateway, failover_active
    if failover_active: return

    print("\n" + "!"*50)
    print("🚨 CONEXIÓN CON AZURE PERDIDA. ACTIVANDO MODO RESCATE 🚨")
    print("!"*50 + "\n")

    # 1. Arrancamos TU servidor local usando el log descargado
    print("[LOCAL] Iniciando Servidor de Respaldo...")
    local_process_server = subprocess.Popen(
        [sys.executable, LOCAL_SERVER, str(AZURE_PORT), LOG_FILE]
    )

    # 2. Arrancamos el Gateway local
    print("[LOCAL] Iniciando Gateway Web...")
    local_process_gateway = subprocess.Popen(
        [sys.executable, LOCAL_GATEWAY]
    )
    
    failover_active = True
    print("\n✅ SISTEMA LOCAL OPERATIVO en http://localhost:8080")

def deactivate_failover():
    global local_process_server, local_process_gateway, failover_active
    if not failover_active: return

    print("\n" + "*"*50)
    print("💚 AZURE HA REGRESADO. APAGANDO NODO LOCAL")
    print("*"*50 + "\n")

    if local_process_server: local_process_server.terminate()
    if local_process_gateway: local_process_gateway.terminate()
    
    failover_active = False

def main():
    print(f"--- MONITOR DE ALTA DISPONIBILIDAD (Firewall Bypass) ---")
    print(f"Monitoreando: {AZURE_IP}")
    
    try:
        while True:
            # Usamos el chequeo SSH en lugar del TCP directo
            is_alive = check_azure_via_ssh()

            if is_alive:
                print(f"[HEALTH] Azure ONLINE. ", end="")
                if failover_active:
                    deactivate_failover()
                download_logs() 
            else:
                print(f"[HEALTH] ❌ Azure OFFLINE (No responde SSH).")
                activate_failover()

            time.sleep(5)
    except KeyboardInterrupt:
        if local_process_server: local_process_server.terminate()
        if local_process_gateway: local_process_gateway.terminate()
        print("\nBye!")

if __name__ == "__main__":
    main()