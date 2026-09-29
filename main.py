import os
import time
import json
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ⚙️ CONFIGURACIÓN GOOGLE SHEETS
SPREADSHEET_ID = "1QgVCGkof5R0HUGNY8m0vFem_OZI3doACahx8D7zdc-E"
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
HOJA_DESTINO = "Avisos Bot"

def obtener_servicio_sheets():
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    if not creds_json:
        raise ValueError("❌ ERROR: No se encontró la variable GOOGLE_CREDENTIALS en GitHub Secrets.")
    
    creds_dict = json.loads(creds_json)
    creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return build('sheets', 'v4', credentials=creds)

def obtener_avisos_existentes(servicio):
    try:
        rango = f"'{HOJA_DESTINO}'!A:E"
        result = servicio.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range=rango).execute()
        filas = result.get('values', [])
        registrados = set()
        
        ultima_fila_real = 0
        
        for i, fila in enumerate(filas):
            if any(str(celda).strip() for celda in fila):
                ultima_fila_real = i + 1
                
            if len(fila) >= 4:
                nombre = str(fila[3]).strip()
                detalles = str(fila[4]).strip() if len(fila) >= 5 else ""
                if nombre:
                    registrados.add(f"{nombre} | {detalles}")
                    
        print(f"📂 Se leyeron {len(registrados)} avisos. Última fila ocupada detectada: {ultima_fila_real}")
        
        proxima = ultima_fila_real + 1 if ultima_fila_real > 0 else 1 
        return registrados, proxima
    except Exception as e:
        print(f"⚠️ No se pudo leer el histórico: {e}")
        return set(), 1

def extraer_obituarios_completos():
    fecha_actual = (datetime.utcnow() - timedelta(hours=3)).strftime("%d/%m/%Y")
    servicio_sheets = obtener_servicio_sheets()
    
    avisos_registrados, proxima_fila_vacia = obtener_avisos_existentes(servicio_sheets)

    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")

    print("\n🚀 Iniciando el robot explorador de Empresa Flores...")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

    try:
        # Modificamos el rango para que arranque en la 26 y frene en la 50
        for pagina in range(26, 51):
            datos_nuevos = [] 
            print(f"\n📄 --- LEYENDO PÁGINA {pagina} ---")
            
            # Usamos directamente la URL con paginación
            url_pagina = f"https://empresaflores.com/obituarios/?_empresa=empresa_flores&_avisos_del_dia=past&_paged={pagina}"
            
            driver.get(url_pagina)
            time.sleep(8) 
            
            botones = driver.find_elements(By.XPATH, "//*[contains(translate(text(), 'MÁS INFORMACIÓN', 'más información'), 'más información')]")
            
            if len(botones) == 0:
                print("🛑 No se encontraron más avisos en esta página. Terminando búsqueda.")
                break

            print(f"¡Se encontraron {len(botones)} obituarios en esta página!")

            for i in range(len(botones)):
                try:
                    botones_act = driver.find_elements(By.XPATH, "//*[contains(translate(text(), 'MÁS INFORMACIÓN', 'más información'), 'más información')]")
                    if i >= len(botones_act):
                        break
                        
                    boton = botones_act[i]
                    
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", boton)
                    time.sleep(1)
                    driver.execute_script("arguments[0].click();", boton)
                    time.sleep(3) 

                    btn_cerrar = driver.find_element(By.XPATH, "//*[contains(text(), 'Cerrar') or contains(text(), 'CERRAR')]")
                    modal = btn_cerrar.find_element(By.XPATH, "./ancestor::div[1]") 
                    
                    for _ in range(6): 
                        if "Inicio del velatorio" in modal.text or "Inhumacion" in modal.text or len(modal.text) > 100:
                            break
                        modal = modal.find_element(By.XPATH, "./parent::*")
                    
                    texto_completo = modal.text
                    lineas = [linea.strip() for linea in texto_completo.split('\n') if linea.strip() and linea.strip() not in ['Cerrar', 'CERRAR', '×']]
                    
                    if lineas:
                        nombre_fallecido = lineas[0]
                        detalles = " | ".join(lineas[1:]) 
                        identificador = f"{nombre_fallecido} | {detalles}"
                        
                        if identificador not in avisos_registrados:
                            avisos_registrados.add(identificador)
                            marca_temporal = (datetime.utcnow() - timedelta(hours=3)).strftime("%d/%m/%Y %H:%M:%S")
                            datos_nuevos.append([
                                marca_temporal,
                                "Empresa Flores",
                                fecha_actual,
                                nombre_fallecido,
                                detalles
                            ])
                            print(f"✅ Nuevo aviso: {nombre_fallecido}")

                    driver.execute_script("arguments[0].click();", btn_cerrar)
                    time.sleep(1.5) 
                    
                except Exception as e:
                    webdriver.ActionChains(driver).send_keys(Keys.ESCAPE).perform()
                    time.sleep(1)

            if datos_nuevos:
                print(f"\n☁️ Subiendo {len(datos_nuevos)} registros (a partir de la fila {proxima_fila_vacia})...")
                body = {'values': datos_nuevos}
                rango_destino = f"'{HOJA_DESTINO}'!A{proxima_fila_vacia}:E"
                
                servicio_sheets.spreadsheets().values().update(
                    spreadsheetId=SPREADSHEET_ID,
                    range=rango_destino,
                    valueInputOption="USER_ENTERED",
                    body=body
                ).execute()
                
                print(f"✅ Registros guardados. Ajustando puntero de fila...")
                proxima_fila_vacia += len(datos_nuevos)
            else:
                print(f"\n⚠️ No hay avisos nuevos en la página {pagina} para agregar.")

    except Exception as e:
        print(f"\n❌ Error fatal en la página: {e}")
    finally:
        try:
            driver.quit()
        except:
            pass

if __name__ == "__main__":
    extraer_obituarios_completos()
