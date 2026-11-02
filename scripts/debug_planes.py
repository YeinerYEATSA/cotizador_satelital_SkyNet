import pandas as pd

planes = pd.read_csv('data/planes.csv')
print("Columnas en planes.csv:")
print(planes.columns.tolist())
print("\nDatos:")
print(planes.to_string())

# Detectar columnas de compatibilidad
plan_compat_cols = [
    c for c in planes.columns.tolist()
    if any(k in c.lower() for k in ("banda", "compatibilidad", "satelite", "satellite"))
]
print(f"\nColumnas de compatibilidad detectadas: {plan_compat_cols}")
