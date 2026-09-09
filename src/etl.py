import pandas as pd
import sqlite3
import os
import logging
import time

# Forzar zona horaria de Chile (America/Santiago)
os.environ['TZ'] = 'America/Santiago'
if hasattr(time, 'tzset'):
    time.tzset()

# Configuración de Logging
log_dir = os.path.join("data", "processed")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "etl_execution.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(log_file, mode='a', encoding="utf-8"),
        logging.StreamHandler()
    ]
)

def asignar_region(lat):
    if lat >= -18.5: return "1.- Arica y Parinacota"
    elif lat >= -21.5: return "2.- Tarapacá"
    elif lat >= -26.0: return "3.- Antofagasta"
    elif lat >= -29.0: return "4.- Atacama"
    elif lat >= -32.2: return "5.- Coquimbo"
    elif lat >= -33.9: return "6.- Valparaíso / RM"
    elif lat >= -35.0: return "7.- O'Higgins"
    elif lat >= -36.5: return "8.- Maule"
    elif lat >= -38.5: return "9.- Ñuble / Bío Bío"
    elif lat >= -40.5: return "10.- Araucanía / Los Ríos"
    elif lat >= -44.0: return "11.- Los Lagos"
    elif lat >= -48.0: return "12.- Aysén"
    else: return "13.- Magallanes y Antártica"

def ejecutar_etl():
    logging.info("==========================================================")
    logging.info("=== INICIO DE EJECUCIÓN DEL PIPELINE ETL ===")
    
    csv_filename = "earthquakes_chile.csv"
    raw_path = os.path.join("data", "raw", csv_filename)
    logging.info(f"1. [Ingesta] Extrayendo datos desde: '{raw_path}'")
    
    if not os.path.exists(raw_path):
        err_msg = f"No se encontró el archivo de origen: {raw_path}"
        logging.error(err_msg)
        raise FileNotFoundError(err_msg)

    df_raw = pd.read_csv(raw_path)
    total_inicial = len(df_raw)

    logging.info("2. [Transformación] Estandarizando variables y aplicando controles de calidad...")
    renombres = {
        'Date(UTC)': 'datetime',
        'Latitude': 'latitude',
        'Longitude': 'longitude',
        'Depth': 'depth',
        'Magnitude': 'magnitude'
    }
    df_clean = df_raw.rename(columns=renombres).copy()

    # Controles de Calidad
    columnas_clave = ['latitude', 'longitude', 'magnitude', 'depth', 'datetime']
    df_clean = df_clean.dropna(subset=columnas_clave)
    df_clean = df_clean.drop_duplicates(subset=columnas_clave)
    df_clean = df_clean[
        (df_clean['latitude'].between(-57.0, -17.0)) &
        (df_clean['longitude'].between(-80.0, -60.0)) &
        (df_clean['magnitude'].between(0.0, 10.0)) &
        (df_clean['depth'] >= 0.0)
    ]

    # Mantenimiento de fechas históricas reales
    df_clean['datetime'] = pd.to_datetime(df_clean['datetime'])

    # Ingeniería de Características
    df_clean['año'] = df_clean['datetime'].dt.year
    df_clean['mes'] = df_clean['datetime'].dt.month
    df_clean['fecha_corta'] = df_clean['datetime'].dt.strftime('%Y-%m-%d')
    df_clean['region'] = df_clean['latitude'].apply(asignar_region)

    db_filename = "sismos_analitico.db"
    db_path = os.path.join("data", "processed", db_filename)
    logging.info(f"3. [Carga] Exportando repositorio analítico hacia: '{db_path}'")
    
    conn = sqlite3.connect(db_path)
    df_clean.to_sql("sismos", conn, if_exists="replace", index=False)

    conn.execute("""
    CREATE VIEW IF NOT EXISTS vista_resumen_mensual AS
    SELECT año, mes, COUNT(*) AS total_sismos, ROUND(AVG(magnitude), 2) AS magnitud_promedio, MAX(magnitude) AS magnitud_maxima, ROUND(AVG(depth), 2) AS profundidad_promedio
    FROM sismos GROUP BY año, mes;
    """)

    conn.execute("""
    CREATE VIEW IF NOT EXISTS vista_resumen_regional AS
    SELECT region, COUNT(*) AS total_sismos, ROUND(AVG(magnitude), 2) AS magnitud_promedio, MAX(magnitude) AS magnitud_maxima
    FROM sismos GROUP BY region ORDER BY total_sismos DESC;
    """)

    conn.commit()
    conn.close()
    
    logging.info("=== ETL COMPLETADO CON ÉXITO ===")
    logging.info("==========================================================\n")

if __name__ == "__main__":
    ejecutar_etl()
