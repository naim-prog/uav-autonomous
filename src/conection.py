import subprocess
import sys
import time
import os
import tempfile


def connect_to_wifi(ssid, password, timeout=30):
    if sys.platform == 'linux':
        return _connect_linux(ssid, password, timeout)
    elif sys.platform == 'win32':
        return _connect_windows(ssid, password, timeout)
    else:
        print(f"[WIFI] - Plataforma no soportada: {sys.platform}")
        return False

def _is_connected_linux(ssid):
    try:
        output = subprocess.check_output(
            ["nmcli", "-t", "-f", "ACTIVE,SSID", "dev", "wifi"],
            text=True, stderr=subprocess.DEVNULL
        )
        return any(
            line.startswith("yes:") and ssid in line
            for line in output.strip().splitlines()
        )
    except subprocess.CalledProcessError:
        return False


def _connect_linux(ssid, password, timeout):
    if _is_connected_linux(ssid):
        print(f"[WIFI] - Ya conectado a '{ssid}'.")
        return True

    try:
        perfiles = subprocess.check_output(
            ["nmcli", "-t", "-f", "NAME", "connection", "show"],
            text=True, stderr=subprocess.DEVNULL
        ).strip().splitlines()

        if ssid in perfiles:
            subprocess.check_output(
                ["nmcli", "connection", "up", ssid],
                text=True, stderr=subprocess.STDOUT
            )
        else:
            subprocess.check_output(
                ["nmcli", "device", "wifi", "connect", ssid, "password", password],
                text=True, stderr=subprocess.STDOUT
            )
    except subprocess.CalledProcessError as e:
        print(f"[WIFI] - Error al iniciar conexion: {e.output.strip()}")
        return False

    for _ in range(timeout):
        if _is_connected_linux(ssid):
            print(f"[WIFI] - Conexion exitosa a '{ssid}'.")
            return True
        time.sleep(1)

    print(f"[WIFI] - Timeout: no se pudo conectar a '{ssid}' en {timeout}s.")
    return False


windows_wifi_xml = """<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
    <name>{ssid}</name>
    <SSIDConfig>
        <SSID><name>{ssid}</name></SSID>
    </SSIDConfig>
    <connectionType>ESS</connectionType>
    <connectionMode>auto</connectionMode>
    <MSM>
        <security>
            <authEncryption>
                <authentication>WPA2PSK</authentication>
                <encryption>AES</encryption>
                <useOneX>false</useOneX>
            </authEncryption>
            <sharedKey>
                <keyType>passPhrase</keyType>
                <protected>false</protected>
                <keyMaterial>{password}</keyMaterial>
            </sharedKey>
        </security>
    </MSM>
</WLANProfile>"""


def _is_connected_windows(ssid):
    try:
        output = subprocess.check_output(
            ["netsh", "wlan", "show", "interfaces"],
            text=True, stderr=subprocess.DEVNULL
        )
        return "connected" in output.lower() and ssid in output
    except subprocess.CalledProcessError:
        return False


def _connect_windows(ssid, password, timeout):
    if _is_connected_windows(ssid):
        print(f"[WIFI] - Ya conectado a '{ssid}'.")
        return True

    profile_path = os.path.join(tempfile.gettempdir(), f"wifi_{ssid}.xml")
    try:
        with open(profile_path, 'w', encoding='utf-8') as f:
            f.write(windows_wifi_xml.format(ssid=ssid, password=password))

        subprocess.check_output(
            ["netsh", "wlan", "add", "profile", f"filename={profile_path}"],
            text=True, stderr=subprocess.STDOUT
        )
        subprocess.check_output(
            ["netsh", "wlan", "connect", f"name={ssid}"],
            text=True, stderr=subprocess.STDOUT
        )
    except subprocess.CalledProcessError as e:
        print(f"[WIFI] - Error al conectar: {e.output.strip()}")
        return False
    finally:
        # El XML contiene la contraseña en texto plano, lo borramos
        if os.path.exists(profile_path):
            os.remove(profile_path)

    for _ in range(timeout):
        if _is_connected_windows(ssid):
            print(f"[WIFI] - Conexion exitosa a '{ssid}'.")
            return True
        time.sleep(1)

    print(f"[WIFI] - Timeout: no se pudo conectar a '{ssid}' en {timeout}s.")
    return False