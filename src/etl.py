import pandas as pd
import sqlite3
import os
import logging

# Configuración de Logging con formato de marca de tiempo (Fecha y Hora)
log_dir = os.path.join("data", "processed")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "etl_execution.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(log_file, mode='a', encoding="utf-8"), # 'a' acumula registros con marca de tiempo
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
    logging.info("==========================================================")
    logging.info("=== INICIO DE EJECUCIÓN DEL PIPELINE ETL ===")
    
    # 1. INGESTA
    csv_filename = "earthquakes_chile.csv"
    raw_path = os.path.join("data", "raw", csv_filename)
    logging.info(f"1. [Ingesta] Extrayendo datos desde el archivo de origen: '{raw_path}'")
    
    if not os.path.exists(raw_path):
        err_msg = f"No se encontró el archivo de origen: {raw_path}"
        logging.error(err_msg)
        raise FileNotFoundError(err_msg)

    df_raw = pd.read_csv(raw_path)
    total_inicial = len(df_raw)
    logging.info(f"   [Ingesta] Archivo '{csv_filename}' cargado exitosamente con {total_inicial} registros iniciales.")

    # 2. TRANSFORMACIÓN Y CALIDAD DE DATOS
    logging.info("2. [Transformación] Estandarizando variables y aplicando controles de calidad...")
    renombres = {
        'Date(UTC)': 'datetime',
        'Latitude': 'latitude',
        'Longitude': 'longitude',
        'Depth': 'depth',
        'Magnitude': 'magnitude'
    }
    df_clean = df_raw.rename(columns=renombres).copy()

    # Control de Calidad 1: Detección y eliminación de nulos
    columnas_clave = ['latitude', 'longitude', 'magnitude', 'depth', 'datetime']
    df_clean = df_clean.dropna(subset=columnas_clave)
    descartados_nulos = total_inicial - len(df_clean)
    logging.info(f"   [Calidad - Nulos] Registros descartados por valores nulos en variables clave: {descartados_nulos}")

    # Control de Calidad 2: Eliminación de registros duplicados
    filas_antes_duplicados = len(df_clean)
    df_clean = df_clean.drop_duplicates(subset=columnas_clave)
    descartados_duplicados = filas_antes_duplicados - len(df_clean)
    logging.info(f"   [Calidad - Duplicados] Registros duplicados eliminados: {descartados_duplicados}")

    # Control de Calidad 3: Validaciones de rango geográfico y físico (Reglas de Negocio)
    # Coordenadas válidas para Chile aproximadamente: Latitud [-56, -17], Longitud [-76, -66]
    # Magnitudes plausibles [0, 10], Profundidades positivas [0, 800]
    filas_antes_rangos = len(df_clean)
    df_clean = df_clean[
        (df_clean['latitude'].between(-57.0, -17.0)) &
        (df_clean['longitude'].between(-80.0, -60.0)) &
        (df_clean['magnitude'].between(0.0, 10.0)) &
        (df_clean['depth'] >= 0.0)
    ]
    descartados_outliers = filas_antes_rangos - len(df_clean)
    logging.info(f"   [Calidad - Rangos] Registros fuera de rango válido o anomalías descartadas: {descartados_outliers}")

    total_limpio = len(df_clean)
    logging.info(f"   [Calidad - Resumen] Total de registros aprobados y limpios para procesamiento: {total_limpio} (de {total_inicial} originales)")

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

    # 3. CARGA DE DATOS
    db_filename = "sismos_analitico.db"
    db_path = os.path.join("data", "processed", db_filename)
    logging.info(f"3. [Carga] Exportando repositorio analítico hacia: '{db_path}'")
    
    conn = sqlite3.connect(db_path)
    
    # Carga idempotente (if_exists="replace")
    df_clean.to_sql("sismos", conn, if_exists="replace", index=False)
    logging.info(f"   [Carga - Idempotencia] Tabla 'sismos' actualizada en '{db_filename}' con reescritura segura ('if_exists=replace').")

    # Creación de vistas SQL
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
    
    logging.info(f"=== ETL COMPLETADO CON ÉXITO: Base de datos '{db_filename}' y archivo de auditoría actualizados. ===")
    logging.info("==========================================================\n")

if __name__ == "__main__":
    ejecutar_etl()
