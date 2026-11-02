import pandas as pd

municipios = pd.read_csv('data/municipios.csv')
duplicados = municipios[municipios.duplicated(subset=['municipio'], keep=False)].sort_values('municipio')

print('Total de municipios en el archivo:', len(municipios))
print('Municipios únicos:', municipios['municipio'].nunique())
print('Municipios duplicados:', len(duplicados))
print('\nEjemplos de duplicados:')
print(duplicados.head(30).to_string())
