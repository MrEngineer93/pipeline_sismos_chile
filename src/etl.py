import pandas as pd
import sqlite3
import os
import logging

# Configuración de Logging para guardar en archivo y mostrar en consola
log_dir = os.path.join("data", "processed")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "etl_execution.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler()
    ]
)

def asignar_region(lat):
    if lat >= -18.5: return "Arica y Parinacota"
    elif lat >= -21.5: return "Tarapacá"
    elif lat >= -26.0: return "Antofagasta"
    elif lat >= -29.0: return "Atacama"
    elif lat >= -32.2: return "Coquimbo"
    elif lat >= -33.9: return "Valparaíso / RM"
    elif lat >= -35.0: return "O'Higgins"
    elif lat >= -36.5: return "Maule"
    elif lat >= -38.5: return "Ñuble / Bío Bío"
    elif lat >= -40.5: return "Araucanía / Los Ríos"
    elif lat >= -44.0: return "Los Lagos"
    elif lat >= -48.0: return "Aysén"
    else: return "Magallanes y Antártica"

def ejecutar_etl():
    logging.info("=== INICIO DE EJECUCIÓN DEL PIPELINE ETL ===")
    logging.info("1. Extrayendo datos desde el CSV...")
    
    raw_path = os.path.join("data", "raw", "earthquakes_chile.csv")
    
    if not os.path.exists(raw_path):
        err_msg = f"No se encontró el archivo de origen: {raw_path}"
        logging.error(err_msg)
        raise FileNotFoundError(err_msg)

    df_raw = pd.read_csv(raw_path)
    total_inicial = len(df_raw)
    logging.info(f"   [Ingesta] Total de registros leídos desde el CSV: {total_inicial}")

    logging.info("2. Estandarizando, limpiando y enriqueciendo variables...")
    renombres = {
        'Date(UTC)': 'datetime',
        'Latitude': 'latitude',
        'Longitude': 'longitude',
        'Depth': 'depth',
        'Magnitude': 'magnitude'
    }
    df_clean = df_raw.rename(columns=renombres).copy()

    # Métrica y métricas de calidad de datos
    columnas_clave = ['latitude', 'longitude', 'magnitude', 'depth', 'datetime']
    df_clean = df_clean.dropna(subset=columnas_clave)
    total_limpio = len(df_clean)
    registros_descartados = total_inicial - total_limpio

    logging.info(f"   [Calidad de Datos] Registros con nulos descartados: {registros_descartados}")
    logging.info(f"   [Calidad de Datos] Registros limpios para procesamiento: {total_limpio}")

    # Conversión temporal y simulación a 2026
    df_clean['datetime'] = pd.to_datetime(df_clean['datetime'])
    max_year = df_clean['datetime'].dt.year.max()
    desfase_anos = 2026 - max_year
    df_clean['datetime'] = df_clean['datetime'] + pd.DateOffset(years=desfase_anos)

    # Ingeniería de Características
    df_clean['año'] = df_clean['datetime'].dt.year
    df_clean['mes'] = df_clean['datetime'].dt.month
    df_clean['fecha_corta'] = df_clean['datetime'].dt.strftime('%Y-%m-%d')
    df_clean['region'] = df_clean['latitude'].apply(asignar_region)

    logging.info("3. Cargando datos en el Repositorio Analítico (SQLite)...")
    db_path = os.path.join("data", "processed", "sismos_analitico.db")
    
    conn = sqlite3.connect(db_path)
    
    # Carga idempotente mediante reescritura de tabla
    df_clean.to_sql("sismos", conn, if_exists="replace", index=False)
    logging.info("   [Idempotencia] Carga ejecutada con 'if_exists=replace'. Tabla 'sismos' actualizada sin duplicados.")

    # Vistas SQL
    conn.execute("""
    CREATE VIEW IF NOT EXISTS vista_resumen_mensual AS
    SELECT 
        año,
        mes,
        COUNT(*) AS total_sismos,
        ROUND(AVG(magnitude), 2) AS magnitud_promedio,
        MAX(magnitude) AS magnitud_maxima,
        ROUND(AVG(depth), 2) AS profundidad_promedio
    FROM sismos
    GROUP BY año, mes;
    """)

    conn.execute("""
    CREATE VIEW IF NOT EXISTS vista_resumen_regional AS
    SELECT 
        region,
        COUNT(*) AS total_sismos,
        ROUND(AVG(magnitude), 2) AS magnitud_promedio,
        MAX(magnitude) AS magnitud_maxima
    FROM sismos
    GROUP BY region
    ORDER BY total_sismos DESC;
    """)

    conn.commit()
    conn.close()
    
    logging.info("=== ETL COMPLETADO EXITOSAMENTE CON CUMPLIMIENTO DE IDEMPOTENCIA Y CALIDAD DE DATOS ===")

if __name__ == "__main__":
    ejecutar_etl()
