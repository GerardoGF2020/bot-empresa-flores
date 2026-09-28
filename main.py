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
        rango = f"'{HOJA_DESTINO}'!D:E"
        result = servicio.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range=rango).execute()
        filas = result.get('values', [])
        registrados = set()
        
        for fila in filas[1:]:
            if len(fila) >= 2:
                nombre = fila[0].strip()
                detalles = fila[1].strip()
                registrados.add(f"{nombre} | {detalles}")
                
        print(f"📂 Se leyeron {len(registrados)} avisos históricos desde Google Sheets.")
        return registrados
    except Exception as e:
        print(f"⚠️ No se pudo leer el histórico: {e}")
        return set()

def extraer_obituarios_completos():
    url = "https://empresaflores.com/obituarios/?_empresa=empresa_flores&_avisos_del_dia=past"
    fecha_actual = (datetime.utcnow() - timedelta(hours=3)).strftime("%d/%m/%Y")

    servicio_sheets = obtener_servicio_sheets()
    avisos_registrados = obtener_avisos_existentes(servicio_sheets)
    datos_nuevos = []

    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")

    print("\n🚀 Iniciando el robot explorador de Empresa Flores...")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

    try:
        driver.get(url)
        time.sleep(8) 

        # Recorremos 15 páginas hacia atrás en el tiempo
        for pagina in range(1, 16):
            print(f"\n📄 --- LEYENDO PÁGINA {pagina} ---")
            
            botones = driver.find_elements(By.XPATH, "//*[contains(translate(text(), 'MÁS INFORMACIÓN', 'más información'), 'más información')]")
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
                    time.sleep(2.5) 

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

            # Pasar a la siguiente página numerada
            try:
                # Buscamos el botón 'Siguiente' o la flecha
                btn_siguiente = driver.find_element(By.XPATH, "//a[contains(@class, 'next') or contains(text(), '»') or contains(text(), '›') or contains(translate(text(), 'SIGUIENTE', 'siguiente'), 'siguiente')]")
                print("⏩ Viajando a la siguiente página del historial...")
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn_siguiente)
                time.sleep(1)
                driver.execute_script("arguments[0].click();", btn_siguiente)
                time.sleep(6) 
            except:
                print("🛑 No hay más páginas disponibles.")
                break

        if datos_nuevos:
            print(f"\n☁️ Subiendo {len(datos_nuevos)} registros nuevos a la planilla...")
            body = {'values': datos_nuevos}
            rango_destino = f"'{HOJA_DESTINO}'!A:E"
            servicio_sheets.spreadsheets().values().append(
                spreadsheetId=SPREADSHEET_ID,
                range=rango_destino,
                valueInputOption="USER_ENTERED",
                insertDataOption="INSERT_ROWS",
                body=body
            ).execute()
            print("✅ Planilla actualizada con éxito.")
        else:
            print("\n⚠️ No hay avisos nuevos para agregar.")

    except Exception as e:
        print(f"\n❌ Error fatal en la página: {e}")
    finally:
        try:
            driver.quit()
        except:
            pass

if __name__ == "__main__":
    extraer_obituarios_completos()
