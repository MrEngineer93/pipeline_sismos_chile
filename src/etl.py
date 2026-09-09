import os
import sqlite3
import pandas as pd
import logging

# Configuración de Logging
log_dir = os.path.join("logs")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "pipeline_etl.log")

logging.basicConfig(
    filename=log_file,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

def run_etl():
    logging.info("=" * 60)
    logging.info("=== INICIO DE EJECUCIÓN DEL PIPELINE ETL ===")
    
    # -------------------------------------------------------------
    # 1. INGESTA
    # -------------------------------------------------------------
    csv_path = os.path.join("data", "raw", "earthquakes_chile.csv")
    logging.info(f"1. [Ingesta] Extrayendo datos desde: '{csv_path}'")
    
    if not os.path.exists(csv_path):
        logging.error(f"Error crítico: El archivo '{csv_path}' no existe.")
        return

    df_raw = pd.read_csv(csv_path)
    registros_iniciales = len(df_raw)
    logging.info(f"   [Ingesta] Registros iniciales leídos: {registros_iniciales}")

    # -------------------------------------------------------------
    # 2. TRANSFORMACIÓN & CALIDAD DE DATOS
    # -------------------------------------------------------------
    logging.info("2. [Transformación] Estandarizando variables y aplicando controles de calidad...")
    
    # Copia de trabajo
    df = df_raw.copy()

    # Normalización de nombres de columnas
    df.columns = df.columns.str.strip().str.lower()

    # Conversión de tipos de datos
    df['datetime'] = pd.to_datetime(df['datetime'], errors='coerce')
    df['magnitude'] = pd.to_numeric(df['magnitude'], errors='coerce')
    df['depth'] = pd.to_numeric(df['depth'], errors='coerce')
    df['latitude'] = pd.to_numeric(df['latitude'], errors='coerce')
    df['longitude'] = pd.to_numeric(df['longitude'], errors='coerce')

    # Controles de calidad y filtrado
    nulos_iniciales = df.isnull().sum().sum()
    df_clean = df.dropna(subset=['datetime', 'magnitude', 'latitude', 'longitude']).copy()
    nulos_eliminados = registros_iniciales - len(df_clean)

    # Eliminación de duplicados
    duplicados_cantidad = df_clean.duplicated().sum()
    df_clean = df_clean.drop_duplicates()

    # Extracción de variables temporales para analítica
    df_clean['año'] = df_clean['datetime'].dt.year
    df_clean['mes'] = df_clean['datetime'].dt.month
    df_clean['dia'] = df_clean['datetime'].dt.day
    df_clean['hora'] = df_clean['datetime'].dt.hour

    registros_validos = len(df_clean)
    registros_descartados = registros_iniciales - registros_validos

    logging.info(f"   [Calidad de Datos] Nulos eliminados: {nulos_eliminados}")
    logging.info(f"   [Calidad de Datos] Duplicados eliminados: {duplicados_cantidad}")
    logging.info(f"   [Calidad de Datos] Registros totales descartados: {registros_descartados}")
    logging.info(f"   [Calidad de Datos] Registros válidos procesados: {registros_validos}")

    # -------------------------------------------------------------
    # 3. CARGA (REPOSITORY SINK)
    # -------------------------------------------------------------
    db_dir = os.path.join("data", "processed")
    os.makedirs(db_dir, exist_ok=True)
    db_filename = "sismos_analitico.db"
    db_path = os.path.join(db_dir, db_filename)

    logging.info(f"3. [Carga] Exportando repositorio analítico hacia: '{db_path}'")
    
    # Verificación previa para log dinámico
    db_existe = os.path.exists(db_path)
    accion_db = "actualizada" if db_existe else "creada"

    conn = sqlite3.connect(db_path)
    df_clean.to_sql("sismos", conn, if_exists="replace", index=False)
    conn.close()

    logging.info(f"   [Carga - Idempotencia] Tabla 'sismos' {accion_db} en '{db_filename}' con reescritura segura ('if_exists=replace').")
    logging.info(f"=== ETL COMPLETADO CON ÉXITO: Base de datos '{db_filename}' y archivo de auditoría actualizados. ===")
    logging.info("=" * 60 + "\n")

if __name__ == "__main__":
    run_etl()
