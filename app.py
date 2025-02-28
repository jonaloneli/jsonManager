import os
import json
import paramiko
from flask import Flask, request, jsonify, render_template
from datetime import datetime
import tempfile
import traceback
from flask import Response
import pandas as pd
from io import BytesIO
import xlsxwriter
import subprocess
import threading
import webbrowser
# from pystray import Icon, Menu, MenuItem
# from PIL import Image, ImageDraw
import ctypes
import sys
import atexit
import time



app = Flask(__name__)
from flask import Flask, request, jsonify, render_template, redirect, url_for, session, flash
from datetime import timedelta

app = Flask(__name__)
app.secret_key = "supersecretkey"  # Necesaria para firmar las cookies de sesión
app.permanent_session_lifetime = timedelta(minutes=30)  # Tiempo de expiración de sesión

# Datos de autenticación
USERNAME = "Admin"
PASSWORD = "Sistem2024"

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if username == USERNAME and password == PASSWORD:
            session.permanent = True  # Hacer la sesión permanente
            session['user'] = username  # Guardar el usuario en la sesión
            flash('Inicio de sesión exitoso', 'success')
            return redirect(url_for('index'))  # Redirigir a la página principal
        else:
            flash('Usuario o contraseña incorrectos', 'danger')
            return redirect(url_for('login'))
    
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('user', None)  # Eliminar el usuario de la sesión
    flash('Has cerrado sesión', 'danger')
    return redirect(url_for('login'))

@app.route('/')
def index():
    if 'user' in session:
        return render_template('index.html')
    else:
        flash('Por favor, inicia sesión primero', 'warning')
        return redirect(url_for('login'))

# @app.route('/cameras')
# def cameras():
#     if 'user' in session:
#         carpeta_existe = os.path.exists('../static/img/folder')
#         return render_template('cameras.html', vms=vms, carpeta_existe=carpeta_existe)
#     else:
#         flash('Por favor, inicia sesión primero', 'warning')
#         return redirect(url_for('login'))


# Funciones para mostrar y ocultar la consola
def hide_console():
    if os.name == 'nt':
        ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)


# Ocultar la consola inicialmente
hide_console()

# Obtener la ruta del directorio base del script
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

selected_vm = None  # Variable global para almacenar la MV seleccionada

# Datos de conexión a las MVs
vms = [
    {"ip": "IP SERVIDOR 1", "user": "administrador", "password": "Admin@1", "folders": ["CARPETA1", "CARPETA2"]},
    {"ip": "IP SERVIDOR 2", "user": "administrador", "password": "Admin@1", "folders": ["CARPETA1", "CARPETA2", "CARPETA3"]},
    {"ip": "IP SERVIDOR 3", "user": "administrador", "password": "Admin@1", "folders": ["CARPETA1", "CARPETA2", "CARPETA3"]},
    {"ip": "IP SERVIDOR 4", "user": "administrador", "password": "Admin@1", "folders": ["CARPETA1", "CARPETA2", "CARPETA3", "CARPETA4"]},
]

base_path = "C:\ruta\carpeta"
json_filename = "archivo.json"

##########################################################


# Ruta del archivo de bloqueo
lock_file = "browser_lock.txt"

def check_and_open_browser():
    if not os.path.exists(lock_file):
        print("Abriendo el navegador...")
        webbrowser.open_new("http://127.0.0.1:5000/")
        # Crear el archivo de bloqueo para indicar que el navegador se ha abierto
        with open(lock_file, 'w') as f:
            f.write("browser_opened")
        print("Navegador abierto.")
        # Iniciar un hilo que monitoree el navegador y elimine el archivo de bloqueo cuando el navegador se cierre
        threading.Thread(target=monitor_browser).start()
    else:
        # Si el archivo ya existe, eliminarlo directamente
        os.remove(lock_file)

def monitor_browser():
    while True:
        time.sleep(1)  # Verificar cada segundo
        # Verificar si hay algún navegador abierto con la URL específica
        if not is_browser_open():
            if os.path.exists(lock_file):
                os.remove(lock_file)
            break

def is_browser_open():
    # Esta función debe implementar la lógica para verificar si hay un navegador abierto con la URL específica
    # En esta implementación, asumimos que siempre se cierra correctamente después de abrir
    # Debes ajustar esto según tu entorno y navegador
    return any("127.0.0.1:5000" in proc for proc in os.popen('tasklist').read().splitlines())

# Abrir el navegador automáticamente después de 1 segundo
timer = threading.Timer(1, check_and_open_browser)
timer.start()

###########################################################

def connect_to_vm(ip, user, password):
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(ip, username=user, password=password, timeout=15)  # Establece un tiempo de espera de 15 segundos
        return ssh
    except Exception as e:
        return str(e)

@app.route('/select_vm', methods=['POST'])
def select_vm():
    global selected_vm
    selected_vm = request.json.get('selected_vm')
    
    # Si se selecciona "all", dejamos selected_vm en None para procesar todas las VMs
    if selected_vm == "all":
        selected_vm = None
    
    return jsonify({"status": "success"})



def fetch_json_files():
    all_json_files = []
    errors = []

    temp_dir = tempfile.gettempdir()
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)

    if selected_vm:  # Si se ha seleccionado una MV
        vm = next((vm for vm in vms if vm["ip"] == selected_vm), None)
        if vm is None:
            return [], [f"No se encontró la MV seleccionada: {selected_vm}"]
        vms_to_process = [vm]
    else:
        vms_to_process = vms

    for vm in vms_to_process:
        print(f"Processing VM {vm['ip']}")
        connection = connect_to_vm(vm["ip"], vm["user"], vm["password"])
        if isinstance(connection, str):
            errors.append(f"No se pudo conectar a la MV {vm['ip']}: {connection}")
            continue
        ssh = connection
        sftp = ssh.open_sftp()
        for folder in vm["folders"]:
            json_path = os.path.join(base_path, folder, json_filename)
            local_path = os.path.join(temp_dir, folder, json_filename)
            print(f"Fetching {json_path} from VM {vm['ip']} to {local_path}")
            try:
                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                sftp.get(json_path, local_path)
                print(f"Downloaded {json_path} to {local_path}")
                all_json_files.append(local_path)
            except FileNotFoundError as e:
                errors.append(f"No se encontró el archivo {json_path} en la MV {vm['ip']}: {str(e)}")
            except Exception as e:
                errors.append(f"Error al obtener el archivo {json_path} de la MV {vm['ip']}: {str(e)}")
        sftp.close()
        ssh.close()
    return all_json_files, errors

def search_identifier(identifier, json_files):
    found_files = []
    found_data = []
    for json_file in json_files:
        try:
            with open(json_file, 'r', encoding='utf-8-sig') as file:
                data = json.load(file)
                for transcoder in data:
                    for camera in transcoder.get('Video transcoder information', {}).get('Video sources', []):
                        if camera.get('Identifier') == identifier:
                            found_files.append(json_file)
                            found_data.append(camera)
                            break
        except Exception as e:
            print(f"Error al leer o procesar el JSON  {json_file}: {e}")
            continue
    return found_files, found_data


def backup_files(identifier, note):
    if not selected_vm:
        return [], ["No se ha seleccionado ningun servidor para realizar la copia de seguridad."]
    
    timestamp = datetime.now().strftime("%d%m%Y_%H-%M")
    json_files, errors = fetch_json_files()
    files_to_backup, _ = search_identifier(identifier, json_files)
    
    for json_file in files_to_backup:
        folder_name = os.path.basename(os.path.dirname(json_file))
        vm_info = next((v for v in vms if folder_name in v["folders"]), None)
        if vm_info is None:
            errors.append(f"No se encontró el servidor para la carpeta {folder_name}")
            continue
        
        if vm_info["ip"] != selected_vm:
            errors.append(f"El archivo {json_file} pertenece a un servidor diferente al seleccionado.")
            continue
        
        connection = connect_to_vm(vm_info["ip"], vm_info["user"], vm_info["password"])
        if isinstance(connection, str):
            errors.append(f"No se pudo conectar al servidor {vm_info['ip']}: {connection}")
            continue
        ssh = connection
        sftp = ssh.open_sftp()
        backup_folder = os.path.join(base_path, "Historic servers", folder_name, f"{timestamp}")
        try:
            sftp.mkdir(backup_folder)
        except OSError:
            pass
        filename = os.path.basename(json_file)
        remote_backup_path = os.path.join(backup_folder, filename)
        try:
            sftp.put(json_file, remote_backup_path)
        except Exception as e:
            errors.append(f"Error al guardar el archivo de respaldo en {remote_backup_path}: {str(e)}")

        remote_note_path = os.path.join(backup_folder, "backup_note.txt")
        try:
            with sftp.file(remote_note_path, 'w') as file:
                file.write(note.replace('\n', '\r\n'))
        except Exception as e:
            errors.append(f"Error al guardar la nota de respaldo en {remote_note_path}: {str(e)}")
                
        sftp.close()
        ssh.close()
    return base_path, errors



def update_json_file(json_file, identifier, new_data):
    try:
        with open(json_file, 'r+', encoding='utf-8-sig') as file:
            data = json.load(file)
            found = False
            print(f"Actualizando archivo: {json_file} con nuevos datos: {new_data}")  # Registro
            for transcoder in data:
                for camera in transcoder.get('Video transcoder information', {}).get('Video sources', []):
                    if camera.get('Identifier') == identifier:
                        camera.update(new_data)
                        found = True
            if found:
                file.seek(0)
                json.dump(data, file, indent=4)
                file.truncate()
            else:
                print(f"Identificador {identifier} no encontrado en el archivo {json_file}")
                return f"Identificador {identifier} no encontrado en el archivo {json_file}"
    except Exception as e:
        print(f"Error al actualizar archivo: {json_file} con los nuevos datos: {new_data}, error: {str(e)}")
        return str(e)



def save_changes(json_files, identifier, new_data):
    errors = []
    for json_file in json_files:
        folder = os.path.basename(os.path.dirname(json_file))
        
        vm_info = next((vm for vm in vms if folder in vm["folders"]), None)
        
        if vm_info is None:
            errors.append(f"Servidor no encontrado con la carpeta {folder} con el archivo {json_file}")
            continue
        
        if vm_info["ip"] != selected_vm:
            errors.append(f"El archivo {json_file} pertenece a un servidor diferente al seleccionado.")
            continue
        
        result = update_json_file(json_file, identifier, new_data)
        if result:
            errors.append(result)
            continue
        
        ssh = connect_to_vm(vm_info["ip"], vm_info["user"], vm_info["password"])
        if isinstance(ssh, str):
            errors.append(f"Error de conexión con el servidor {vm_info['ip']}: {ssh}")
            continue
        
        try:
            sftp = ssh.open_sftp()
            sftp.put(json_file, os.path.join(base_path, folder, json_filename))
            sftp.close()
        except Exception as e:
            errors.append(f"Error al actualizar el archivo en el servidor {vm_info['ip']}: {str(e)}")
        ssh.close()
    return errors



# @app.route('/')
# def index():
#     return render_template('index.html')

@app.route('/search', methods=['POST'])
def search():
    identifier = request.form['identifier']
    json_files, errors = fetch_json_files()
    json_file, data = search_identifier(identifier, json_files)
    origins = []
    if json_file:
        for jf in json_file:
            origin_info = next((vm for vm in vms if any(folder in jf for folder in vm["folders"])), None)
            if origin_info:
                origins.append({
                    "ip": origin_info["ip"],
                    "folder": os.path.basename(os.path.dirname(jf))
                })
        return jsonify({"status": "success", "data": data, "origins": origins, "errors": errors})
    else:
        return jsonify({"status": "not_found", "errors": errors})

@app.route('/modify', methods=['POST'])
def modify():
    try:
        data = request.get_json()
        print("Request data:", data)
        identifier = data['identifier']
        new_data = data['new_data']
        json_files, fetch_errors = fetch_json_files()
        print("JSON files:", json_files)
        print("Fetch errors:", fetch_errors)
        modify_errors = save_changes(json_files, identifier, new_data)
        print("Modify errors:", modify_errors)
        all_errors = fetch_errors + modify_errors
        if all_errors:
            response = jsonify({"status": "error", "errors": all_errors})
            print("Response with errors:", response.get_data(as_text=True))
            return response, 500
        response = jsonify({"status": "success", "errors": []})
        print("Successful response:", response.get_data(as_text=True))
        return response
    except Exception as e:
        traceback.print_exc()
        error_message = str(e)
        print("Exception occurred:", error_message)
        response = jsonify({"status": "error", "errors": [error_message]})
        return response, 500


@app.route('/backup', methods=['POST'])
def backup():
    identifier = request.form['identifier']
    note = request.form['note']
    backup_folder, errors = backup_files(identifier, note)
    return jsonify({"status": "success", "backup_folder": backup_folder, "errors": errors})

@app.route('/get_code_block', methods=['POST'])
def get_code_block():
    identifier = request.form['identifier']
    json_files, errors = fetch_json_files()
    _, data = search_identifier(identifier, json_files)
    if data:
        return jsonify({"status": "success", "code_block": data, "errors": errors})
    else:
        return jsonify({"status": "not_found", "errors": errors})


#  ///////////////// LISTAR CAMARAS /////////////////////////
@app.route('/open_vlc', methods=['POST'])
def open_vlc():
    data = request.json
    command = data.get('command')
    
    if not command:
        return Response("Comando no proporcionado", status=400)

    try:
        subprocess.Popen(command, shell=True)
        return Response("VLC abierto con éxito", status=200)
    except Exception as e:
        return Response(f"Error al abrir VLC: {str(e)}", status=500)

@app.route('/cameras', methods=['GET'])
def cameras():
        # Verificar si la carpeta existe
    carpeta_existe = os.path.exists('../static/img/folder')   
    if 'user' in session:
        carpeta_existe = os.path.exists('../static/img/folder')
        return render_template('cameras.html', vms=vms, carpeta_existe=carpeta_existe)
    else:
        flash('Por favor, inicia sesión primero', 'warning')
        return redirect(url_for('login'))

@app.route('/get_cameras', methods=['POST'])
def get_cameras():
    ip = request.form['ip']
    folder = request.form['folder']
    
    vm_info = next((vm for vm in vms if vm["ip"] == ip and folder in vm["folders"]), None)
    
    if not vm_info:
        return Response("Selecciona una carpeta", status=404)
    
    connection = connect_to_vm(vm_info["ip"], vm_info["user"], vm_info["password"])
    if isinstance(connection, str):
        return Response(f"No se pudo conectar al servidor {vm_info['ip']}: {connection}", status=500)
    
    ssh = connection
    sftp = ssh.open_sftp()
    json_path = os.path.join(base_path, folder, json_filename)
    try:
        with sftp.file(json_path, 'r') as file:
            data = json.load(file)
            cameras = []
            for transcoder in data:
                for camera in transcoder.get('Video transcoder information', {}).get('Video sources', []):
                    identifier = camera.get('Identifier').replace('camera.', 'TV ')
                    mrl = camera.get('mrl')  # Asegúrate de que el JSON tiene esta clave
                    cameras.append({
                        "name": identifier,
                        "mrl": mrl
                    })
    except FileNotFoundError as e:
        return Response(f"No se encontró el archivo {json_path} en el servidor {vm_info['ip']}.", status=404)
    except Exception as e:
        return Response(f"Error al obtener el archivo {json_path} del servidor {vm_info['ip']}: {str(e)}", status=500)
    finally:
        sftp.close()
        ssh.close()

    return jsonify({"cameras": cameras})


@app.route('/download_cameras', methods=['POST'])
def download_cameras():
    ip = request.form['ip']
    folder = request.form['folder'] 
    
    vm_info = next((vm for vm in vms if vm["ip"] == ip and folder in vm["folders"]), None)
    
    if not vm_info:
        return Response("Servidor o carpeta no encontrado", status=404)
    
    connection = connect_to_vm(vm_info["ip"], vm_info["user"], vm_info["password"])
    if isinstance(connection, str):
        return Response(f"No se pudo conectar al servidor {vm_info['ip']}: {connection}", status=500)
    
    ssh = connection
    sftp = ssh.open_sftp()
    json_path = os.path.join(base_path, folder, json_filename)
    try:
        with sftp.file(json_path, 'r') as file:
            data = json.load(file)
            cameras = []
            for transcoder in data:
                for camera in transcoder.get('Video transcoder information', {}).get('Video sources', []):
                    identifier = camera.get('Identifier')
                    osd = camera.get('OSD', '')  # Obtener el OSD, si está disponible
                    # Formatear el identificador al formato "TV Número"
                    formatted_identifier = f"TV {identifier.split('.')[1]}"
                    cameras.append({"identifier": formatted_identifier, "osd": osd})
    except FileNotFoundError as e:
        return Response(f"No se encontró el archivo {json_path} en el servidor {vm_info['ip']}.", status=404)
    except Exception as e:
        return Response(f"Error al obtener el archivo {json_path} del servidor {vm_info['ip']}: {str(e)}", status=500)
    finally:
        sftp.close()
        ssh.close()

    # Crear un archivo Excel usando xlsxwriter
    output = BytesIO()
    workbook = xlsxwriter.Workbook(output)
    worksheet = workbook.add_worksheet()

    # Escribir los encabezados de las columnas
    worksheet.write(0, 0, 'Número de Camara')
    worksheet.write(0, 1, 'Ubicación')

    # Escribir los datos en el archivo Excel
    for row_num, camera in enumerate(cameras, start=1):
        worksheet.write(row_num, 0, camera['identifier'])
        worksheet.write(row_num, 1, camera['osd'])

    workbook.close()  # Cerrar el libro de trabajo

    output.seek(0)

    # Modificar el nombre del archivo
    filename = f"TV_{ip}_{folder}.xlsx"

    return Response(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    headers={"Content-Disposition": f"attachment; filename={filename}"})                   

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)