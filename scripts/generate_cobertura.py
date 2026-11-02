import pandas as pd
import random
import os

# Cambiar a directorio de la app
app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(app_dir)

# Cargar municipios
municipios_df = pd.read_csv('data/municipios.csv')

# Definir opciones para cobertura
bandas = ['KU', 'KA', 'L', 'C']
satelites = ['Satelital Hughes', 'Satelital Starlink', 'Satelital Iridium', 'Satelital Inmarsat']

# Crear cobertura para cada municipio - GARANTIZAR que TODOS tengan al menos una
cobertura_data = []
for idx, row in municipios_df.iterrows():
    municipio = row['municipio']
    departamento = row['departamento']
    zona = row['zona']
    
    # Generar 1-2 opciones de cobertura por municipio
    # Usar idx como seed para reproducibilidad pero variar por municipio
    random.seed(idx)
    num_opciones = random.choice([1, 2])
    
    for i in range(num_opciones):
        banda = random.choice(bandas)
        satelite = random.choice(satelites)
        # Crear ID de beam único
        beam = f"{zona[:3].upper()}-{idx+1:04d}-{i+1:03d}"
        
        cobertura_data.append({
            'municipio': municipio,
            'departamento': departamento,
            'banda': banda,
            'satelite': satelite,
            'beam': beam,
            'zona': zona
        })

# Crear DataFrame y guardar
cobertura_df = pd.DataFrame(cobertura_data)
cobertura_df.to_csv('data/cobertura.csv', index=False, encoding='utf-8')

print(f"✅ Cobertura generada para {len(municipios_df)} municipios")
print(f"Total de registros de cobertura: {len(cobertura_df)}")
print(f"Municipios únicos con cobertura: {cobertura_df['municipio'].nunique()}")

# Verificar que no falta ninguno
municipios_sin_cobertura = set(municipios_df['municipio']) - set(cobertura_df['municipio'])
if municipios_sin_cobertura:
    print(f"⚠️  Municipios sin cobertura: {len(municipios_sin_cobertura)}")
    print(municipios_sin_cobertura)
else:
    print("✅ TODOS los municipios tienen cobertura")

print("\nPrimeros registros:")
print(cobertura_df.head(10))
