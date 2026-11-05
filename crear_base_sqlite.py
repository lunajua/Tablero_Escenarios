import pandas as pd
import sqlite3
import os

excel_file = 'TASA 2025 A 08.2026.xlsx'
db_file = 'base_tasa.db'

print(f"Leyendo hoja contable desde {excel_file}...")
df = pd.read_excel(excel_file, sheet_name='BASE 2025 A 08,2026')

# Limpiar tipos de datos y nombres
if 'dfecha' in df.columns:
    df['dfecha'] = pd.to_datetime(df['dfecha']).dt.strftime('%Y-%m-%d')

print(f"Guardando {len(df):,} registros en {db_file}...")
conn = sqlite3.connect(db_file)
df.to_sql('movimientos', conn, if_exists='replace', index=False)

# Crear índices para optimizar filtros en Streamlit
cursor = conn.cursor()
cursor.execute('CREATE INDEX IF NOT EXISTS idx_zona ON movimientos ("Zona Tasa");')
cursor.execute('CREATE INDEX IF NOT EXISTS idx_cuenta ON movimientos ("Cuenta agrupada");')
cursor.execute('CREATE INDEX IF NOT EXISTS idx_tipo ON movimientos ("Tipo Tasa");')
cursor.execute('CREATE INDEX IF NOT EXISTS idx_fecha ON movimientos ("dfecha");')
conn.commit()
conn.close()

db_size_mb = os.path.getsize(db_file) / (1024 * 1024)
print(f"Listo. Base SQLite creada con éxito: {db_file} ({db_size_mb:.2f} MB)")
