from flask import Flask, render_template, request, jsonify, redirect, session, send_file
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    logout_user,
    login_required,
    current_user
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

import pandas as pd
import os
import re
import unicodedata
from io import BytesIO
from datetime import timedelta
from functools import wraps
from sqlalchemy import inspect, text


# =========================================================
# CONFIGURACIÓN
# =========================================================

app = Flask(__name__)

app.secret_key = os.environ.get("SECRET_KEY", "clave-desarrollo-bitacora6")

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "0") == "1",
    PERMANENT_SESSION_LIFETIME=timedelta(minutes=30),
)

# Base de datos local para esta versión
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///cotizador_bitacora6.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


# =========================================================
# FLASK LOGIN
# =========================================================

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


# =========================================================
# MODELO DE USUARIO
# =========================================================

class User(UserMixin, db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    username = db.Column(
        db.String(100),
        unique=True,
        nullable=False
    )

    password = db.Column(
        db.String(200),
        nullable=False
    )

    role = db.Column(
        db.String(20),
        nullable=False,
        default="usuario",
        server_default="usuario"
    )


@login_manager.user_loader
def load_user(user_id):

    return User.query.get(int(user_id))


def admin_required(view):

    @wraps(view)
    @login_required
    def wrapped_view(*args, **kwargs):
        if current_user.role != "admin":
            return "No tiene permisos de administrador", 403
        return view(*args, **kwargs)

    return wrapped_view


# =========================================================
# CREAR BASE DE DATOS
# =========================================================

with app.app_context():

    db.create_all()

    # Compatibilidad con bases SQLite creadas antes de incorporar roles.
    user_columns = {column["name"] for column in inspect(db.engine).get_columns("user")}
    if "role" not in user_columns:
        with db.engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE user ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'usuario'")
            )

    admin_username = os.environ.get("ADMIN_USERNAME", "").strip()
    admin_password = os.environ.get("ADMIN_PASSWORD", "")
    if bool(admin_username) != bool(admin_password):
        raise RuntimeError("Defina ADMIN_USERNAME y ADMIN_PASSWORD para crear el administrador")
    if admin_username and admin_password:
        admin_user = User.query.filter_by(username=admin_username).first()
        if admin_user is None:
            admin_user = User(
                username=admin_username,
                password=generate_password_hash(admin_password),
                role="admin",
            )
            db.session.add(admin_user)
        else:
            admin_user.password = generate_password_hash(admin_password)
            admin_user.role = "admin"
        db.session.commit()


# =========================================================
# RUTAS DE ARCHIVOS
# =========================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

municipios_path = os.path.join(
    BASE_DIR,
    "data",
    "municipios.csv"
)

cobertura_path = os.path.join(
    BASE_DIR,
    "data",
    "cobertura.csv"
)

planes_path = os.path.join(
    BASE_DIR,
    "data",
    "planes.csv"
)

DATA_FILES = {
    "municipios": (municipios_path, {"departamento", "municipio", "zona"}),
    "cobertura": (cobertura_path, {"municipio", "departamento", "banda", "satelite", "beam", "zona"}),
    "planes": (planes_path, {"nombre", "capacidad", "antena", "modem", "precio_usd", "bandas", "satelite"}),
}


# =========================================================
# CARGAR CSV
# =========================================================

def cargar_csv(ruta):

    # intentar UTF-8 primero y luego Latin-1 para evitar problemas de codificación
    encodings_to_try = ["utf-8", "latin1"]

    for enc in encodings_to_try:
        try:
            df = pd.read_csv(ruta, encoding=enc)
            df.columns = (
                df.columns
                .str.strip()
                .str.lower()
                .str.replace(" ", "_")
            )
            return df
        except UnicodeDecodeError:
            # probar siguiente encoding
            continue
        except Exception as e:
            print("Error cargando:", ruta)
            print(e)
            return pd.DataFrame()

    # último recurso: intentar sin especificar encoding
    try:
        df = pd.read_csv(ruta)
        df.columns = (
            df.columns
            .str.strip()
            .str.lower()
            .str.replace(" ", "_")
        )
        return df
    except Exception as e:
        print("Error cargando:", ruta)
        print(e)
        return pd.DataFrame()


municipios = cargar_csv(municipios_path)

cobertura = cargar_csv(cobertura_path)

planes = cargar_csv(planes_path)


def normalizar_datos():

    global municipios, cobertura, planes

    municipios = cargar_csv(municipios_path)
    cobertura = cargar_csv(cobertura_path)
    planes = cargar_csv(planes_path)

    if not planes.empty:
        planes["bandas"] = planes["bandas"].astype(str).str.strip().str.upper()
        planes["satelite"] = planes["satelite"].astype(str).str.strip()

    if not cobertura.empty:
        cobertura["satelite"] = cobertura["satelite"].astype(str).str.strip()

# Normalizar campos relevantes en los dataframes para comparación
if not planes.empty:
    # normalizar bandas a mayúsculas y satelite a forma limpia
    planes["bandas"] = planes["bandas"].astype(str).str.strip().str.upper()
    planes["satelite"] = planes["satelite"].astype(str).str.strip()

if not cobertura.empty:
    cobertura["satelite"] = cobertura["satelite"].astype(str).str.strip()


@app.route("/admin")
@admin_required
def admin_panel():

    return render_template(
        "admin.html",
        datasets=[
            {
                "key": key,
                "filename": os.path.basename(path),
                "rows": len(cargar_csv(path)),
                "columns": ", ".join(sorted(columns)),
            }
            for key, (path, columns) in DATA_FILES.items()
        ],
    )


@app.route("/admin/cargar-datos", methods=["POST"])
@admin_required
def cargar_datos_admin():

    dataset_key = request.form.get("dataset", "").strip()
    uploaded_file = request.files.get("archivo")

    if dataset_key not in DATA_FILES or not uploaded_file or not uploaded_file.filename:
        return redirect("/admin?error=Seleccione un archivo y un conjunto de datos")

    if not uploaded_file.filename.lower().endswith(".csv"):
        return redirect("/admin?error=Solo se permiten archivos CSV")

    path, required_columns = DATA_FILES[dataset_key]
    try:
        uploaded_data = cargar_csv_from_upload(uploaded_file)
    except ValueError as error:
        return redirect(f"/admin?error={error}")

    missing_columns = required_columns - set(uploaded_data.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        return redirect(f"/admin?error=Faltan columnas obligatorias: {missing}")

    uploaded_file.stream.seek(0)
    uploaded_file.save(path)
    normalizar_datos()
    return redirect("/admin?success=Datos actualizados correctamente")


def cargar_csv_from_upload(uploaded_file):

    uploaded_file.stream.seek(0)
    for encoding in ("utf-8", "latin1"):
        try:
            data = pd.read_csv(uploaded_file.stream, encoding=encoding)
            data.columns = (
                data.columns.str.strip().str.lower().str.replace(" ", "_")
            )
            return data
        except UnicodeDecodeError:
            uploaded_file.stream.seek(0)
    raise ValueError("No se pudo leer el archivo CSV")


def normalizar_columnas_consultas(consultas):

    aliases = {
        "municipio": "municipio",
        "ciudad": "municipio",
        "localidad": "municipio",
        "capacidad": "capacidad",
        "capacidadrequerida": "capacidad",
        "capacidadrequeridambps": "capacidad",
        "capacidadesolicitada": "capacidad",
        "capacidadesolicitadambps": "capacidad",
        "anchodebandacontratadombps": "capacidad",
        "anchodebandacontratado": "capacidad",
        "anchodebandambps": "capacidad",
        "velocidad": "capacidad",
        "velocidadmbps": "capacidad",
        "mbps": "capacidad",
    }

    renamed_columns = {}
    for column in consultas.columns:
        normalized = unicodedata.normalize("NFKD", str(column))
        normalized = "".join(
            character for character in normalized
            if not unicodedata.combining(character)
        )
        normalized = re.sub(r"[^a-zA-Z0-9]", "", normalized).lower()
        if normalized in aliases:
            renamed_columns[column] = aliases[normalized]

    return consultas.rename(columns=renamed_columns)


def normalizar_texto(valor):

    texto = "" if pd.isna(valor) else str(valor)
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(
        character for character in texto
        if not unicodedata.combining(character)
    )
    return " ".join(texto.strip().lower().split())


def convertir_capacidad(valor):

    if pd.isna(valor):
        raise ValueError

    coincidencia = re.search(r"\d+(?:[.,]\d+)?", str(valor))
    if not coincidencia:
        raise ValueError

    return int(float(coincidencia.group(0).replace(",", ".")))


# =========================================================
# REGISTRO
# =========================================================

def validar_password(password):

    return (
        len(password) >= 8
        and any(character.isupper() for character in password)
        and any(character.islower() for character in password)
        and any(character.isdigit() for character in password)
    )


@app.route(
    "/register",
    methods=["GET", "POST"]
)
@admin_required
def register():

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        if not username or not password:

            return render_template(
                "register.html",
                error="Debe ingresar usuario y contraseña"
            )

        if not validar_password(password):

            return render_template(
                "register.html",
                error="La contraseña debe tener mínimo 8 caracteres, una mayúscula, una minúscula y un número"
            )

        usuario_existente = User.query.filter_by(
            username=username
        ).first()

        if usuario_existente:

            return render_template(
                "register.html",
                error="El usuario ya existe"
            )

        password_hash = generate_password_hash(
            password
        )

        nuevo_usuario = User(
            username=username,
            password=password_hash
        )

        db.session.add(
            nuevo_usuario
        )

        db.session.commit()

        return redirect("/login")

    return render_template(
        "register.html"
    )


# =========================================================
# LOGIN
# =========================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        usuario = User.query.filter_by(
            username=username
        ).first()

        if usuario and check_password_hash(
            usuario.password,
            password
        ):

            session.permanent = True
            login_user(usuario)

            return redirect("/")

        return render_template(
            "login.html",
            error="Usuario o contraseña incorrectos"
        )

    return render_template(
        "login.html"
    )


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
@login_required
def logout():

    logout_user()

    return redirect("/login")


# =========================================================
# PÁGINA PRINCIPAL
# =========================================================

@app.route(
    "/",
    methods=["GET", "POST"]
)
@login_required
def index():
    resultado = None

    # preparar lista de municipios para la plantilla, incluyendo datos de cobertura si existen
    cobertura_records = (cobertura.to_dict(orient="records") if not cobertura.empty else [])
    # Crear mapeo usando departamento + municipio como clave (para evitar conflictos con municipios duplicados)
    cobertura_map = {
        (normalizar_texto(r.get("departamento")), normalizar_texto(r.get("municipio"))): r
        for r in cobertura_records
    }
    # También crear un mapeo simple solo por municipio como fallback
    cobertura_map_simple = {
        normalizar_texto(r.get("municipio")): r for r in cobertura_records
    }

    # listas únicas para filtros de banda y satelite
    bandas_options = sorted({(r.get("banda") or "").strip() for r in cobertura_records if r.get("banda")})
    satelite_options = sorted({(r.get("satelite") or "").strip() for r in cobertura_records if r.get("satelite")})
    
    # Crear lista de satélites únicos para mostrar en la sección de Cobertura
    satelites_list = []
    seen_satelites = set()
    for r in cobertura_records:
        sat = (r.get("satelite") or "").strip()
        if sat and sat not in seen_satelites:
            satelites_list.append({"satelite": sat})
            seen_satelites.add(sat)

    municipios_list = []
    for r in (municipios.to_dict(orient="records") if not municipios.empty else []):
        nombre = r.get("municipio") if r.get("municipio") is not None else r.get("nombre")
        departamento = r.get("departamento", "")
        # Buscar primero con departamento + municipio, luego solo por municipio
        key_with_dept = (normalizar_texto(departamento), normalizar_texto(nombre))
        key_simple = normalizar_texto(nombre)
        cov = cobertura_map.get(key_with_dept) or cobertura_map_simple.get(key_simple) or {}
        municipios_list.append({
            "nombre": nombre,
            "beam": cov.get("beam"),
            "satelite": cov.get("satelite"),
            "banda": cov.get("banda"),
        })

    # determinar municipio seleccionado (GET para filtro, POST para cotizar)
    if request.method == "POST":
        selected_municipio = request.form.get("municipio", "").strip()
    else:
        selected_municipio = request.args.get("municipio", "").strip()
    selected_banda = request.args.get("banda", "").strip()
    selected_satelite = request.args.get("satelite", "").strip()

    # manejar POST (cotización)
    if request.method == "POST":

        municipio = selected_municipio

        capacidad_input = request.form.get(
            "capacidad",
            ""
        ).strip()

        if not municipio:

            return render_template(
                "index.html",
                resultado={"error": "Debe ingresar un municipio"},
                municipios=municipios_list,
                coberturas=satelites_list,
                planes=[{**r, "precio": int(r.get("precio")) if r.get("precio") not in (None, "") else r.get("precio")} for r in (planes.to_dict(orient="records") if not planes.empty else [])],
                visible_municipios=municipios_list,
                selected_municipio=selected_municipio,
            )

        if not capacidad_input:

            return render_template(
                "index.html",
                resultado={"error": "Debe ingresar la capacidad"},
                municipios=municipios_list,
                coberturas=satelites_list,
                planes=[{**r, "precio": int(r.get("precio")) if r.get("precio") not in (None, "") else r.get("precio")} for r in (planes.to_dict(orient="records") if not planes.empty else [])],
                visible_municipios=municipios_list,
                selected_municipio=selected_municipio,
            )

        try:
            capacidad = int(capacidad_input)
        except ValueError:
            return render_template(
                "index.html",
                resultado={"error": "La capacidad debe ser un número"},
                municipios=municipios_list,
                coberturas=satelites_list,
                planes=[{**r, "precio": int(r.get("precio")) if r.get("precio") not in (None, "") else r.get("precio")} for r in (planes.to_dict(orient="records") if not planes.empty else [])],
                visible_municipios=municipios_list,
                selected_municipio=selected_municipio,
            )

        resultado = cotizar(municipio, capacidad)

    # preparar visible_municipios según filtro (coincidencia parcial, case-insensitive)
    def municipio_matches(m):
        name = normalizar_texto(m.get("nombre"))
        if selected_municipio and normalizar_texto(selected_municipio) not in name:
            return False
        if selected_banda and (m.get("banda") or "") != selected_banda:
            return False
        if selected_satelite and (m.get("satelite") or "") != selected_satelite:
            return False
        return True

    visible_municipios = [m for m in municipios_list if municipio_matches(m)]

    # preparar lista de planes y filtrar por nombre de plan si se solicita
    plans_list = [
        # Normalizar banda a mayúsculas para mostrar y comparar, y renombrar precio_usd a precio
        {**{**r, "bandas": (r.get('bandas') or '').upper(), "precio": int(r.get("precio_usd")) if r.get("precio_usd") not in (None, "") else None}} for r in (planes.to_dict(orient="records") if not planes.empty else [])
    ]

    selected_plan = request.args.get("plan", "").strip()
    if selected_plan:
        filtered_plans = [p for p in plans_list if selected_plan.lower() in (p.get("nombre") or "").lower()]
    else:
        filtered_plans = plans_list

    # si hay un municipio seleccionado, obtener su cobertura para mostrar en los planes
    coverage_for_selected = None
    if selected_municipio:
        # Buscar en municipios_list para obtener el municipio con su cobertura
        selected_item = next((m for m in municipios_list if normalizar_texto(m.get("nombre")) == normalizar_texto(selected_municipio)), None)
        if selected_item and selected_item.get("satelite"):
            coverage_for_selected = {
                "satelite": selected_item.get("satelite"),
                "banda": selected_item.get("banda"),
                "beam": selected_item.get("beam")
            }

    # Detectar si el CSV de planes incluye columnas que describen compatibilidad
    # con bandas/satelite (por ejemplo 'bandas', 'compatible_bandas', 'satelite').
    plan_compat_cols = [
        c for c in (planes.columns.tolist() if not planes.empty else [])
        if any(k in c for k in ("banda", "bandas", "compatible_banda", "satelite", "satellite", "compatible_satelite"))
    ]

    plans_have_coverage_info = len(plan_compat_cols) > 0

    def plan_matches_coverage(plan_dict):
        # Si no hay columnas de compatibilidad, no filtramos (todo es compatible)
        if not plans_have_coverage_info:
            return True

        # Recolectar posibles valores compatibles desde las columnas detectadas
        compatibles = set()
        for col in plan_compat_cols:
            val = plan_dict.get(col)
            if not val:
                continue
            # asumir lista separada por comas o valor único
            for part in str(val).split(","):
                compatibles.add(part.strip().lower())

        # si el usuario filtró por banda/satelite, respetar esos filtros
        if selected_banda and selected_banda.lower() not in compatibles:
            return False
        if selected_satelite and selected_satelite.lower() not in compatibles:
            return False

        # Solo si el usuario EXPLÍCITAMENTE filtró, comprobar cobertura del municipio
        # Si el usuario no filtró banda ni satélite, mostrar todos los planes
        if not selected_banda and not selected_satelite:
            return True

        # Si hay municipio seleccionado y tenemos su cobertura, comprobarla solo si hay filtros
        if coverage_for_selected and (selected_banda or selected_satelite):
            cov_banda = (coverage_for_selected.get("banda") or "").strip().lower()
            cov_satelite = (coverage_for_selected.get("satelite") or "").strip().lower()
            if cov_banda and cov_banda not in compatibles:
                return False
            if cov_satelite and cov_satelite not in compatibles:
                return False

        return True

    # Aplicar filtrado por compatibilidad si procede
    if plans_have_coverage_info:
        filtered_plans = [p for p in filtered_plans if plan_matches_coverage(p)]

    # si hay un municipio seleccionado, obtener su cobertura para mostrar en los planes
    coverage_for_selected = None
    if selected_municipio:
        # Buscar en municipios_list para obtener el municipio con su cobertura
        selected_item = next((m for m in municipios_list if normalizar_texto(m.get("nombre")) == normalizar_texto(selected_municipio)), None)
        if selected_item and selected_item.get("satelite"):
            coverage_for_selected = {
                "satelite": selected_item.get("satelite"),
                "banda": selected_item.get("banda"),
                "beam": selected_item.get("beam")
            }

    # Comprobar desajustes entre los nombres de satélite en `planes` y los de `cobertura`
    satelites_en_planes = { (p.get('satelite') or '').strip() for p in plans_list }
    satelites_en_cobertura = { (c.get('satelite') or '').strip() for c in cobertura_records }
    satelites_mismatch = sorted([s for s in satelites_en_planes if s and s not in satelites_en_cobertura])

    # Si se han filtrado banda/satelite pero no seleccionado municipio, también filtrar los planes
    if (selected_banda or selected_satelite) and not coverage_for_selected:
        # no coverage per plan, so keep plans unchanged
        pass

    return render_template(
        "index.html",
        resultado=resultado,
        municipios=municipios_list,
        coberturas=satelites_list,
        planes=filtered_plans,
        all_plans=plans_list,
        visible_municipios=visible_municipios,
        selected_municipio=selected_municipio,
        selected_plan=selected_plan,
        bandas_options=bandas_options,
        satelite_options=satelite_options,
        selected_banda=selected_banda,
        selected_satelite=selected_satelite,
        plans_have_coverage_info=plans_have_coverage_info,
        satelites_mismatch=satelites_mismatch,
    )


@app.route("/descargar_preoferta")
@login_required
def descargar_preoferta():

    municipio = request.args.get("municipio", "").strip()
    capacidad_input = request.args.get("capacidad", "").strip()

    if not municipio or not capacidad_input:
        return "Debe indicar municipio y capacidad", 400

    try:
        capacidad = int(capacidad_input)
    except ValueError:
        return "La capacidad debe ser un número", 400

    resultado = cotizar(municipio, capacidad)
    if resultado.get("error"):
        return resultado["error"], 400

    preoferta = pd.DataFrame([{
        "Municipio": resultado["municipio"],
        "Beam": resultado["beam"],
        "Satélite": resultado["satelite"],
        "Banda": resultado["banda"],
        "Plan": resultado["plan"],
        "Capacidad a aprovisionar (Mbps)": resultado["capacidad"],
        "Antena": resultado["antena"],
        "Módem": resultado["modem"],
        "Costo mensual (USD)": resultado["costo_usd"],
        "Estado": "Cobertura y capacidad confirmadas",
    }])

    archivo = BytesIO()
    with pd.ExcelWriter(archivo, engine="openpyxl") as writer:
        preoferta.to_excel(writer, index=False, sheet_name="Preoferta")
    archivo.seek(0)

    return send_file(
        archivo,
        as_attachment=True,
        download_name="preoferta_sky_net.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.route("/cargar_consultas_masivas", methods=["POST"])
@login_required
def cargar_consultas_masivas():

    uploaded_file = request.files.get("archivo_consultas")
    if not uploaded_file or not uploaded_file.filename:
        return "Seleccione un archivo de consultas", 400

    extension = os.path.splitext(uploaded_file.filename.lower())[1]
    if extension not in (".csv", ".xlsx"):
        return "El archivo debe ser CSV o Excel (.xlsx)", 400

    try:
        if extension == ".xlsx":
            consultas = pd.read_excel(uploaded_file)
        else:
            consultas = cargar_csv_from_upload(uploaded_file)
    except Exception:
        return "No se pudo leer el archivo de consultas", 400

    consultas = normalizar_columnas_consultas(consultas)
    required_columns = {"municipio", "capacidad"}
    missing_columns = required_columns - set(consultas.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        detected = ", ".join(str(column) for column in consultas.columns)
        return f"Faltan columnas obligatorias: {missing}. Columnas detectadas: {detected}", 400

    result_columns = [
        "Municipio",
        "Beam",
        "Satélite",
        "Banda",
        "Plan",
        "Capacidad solicitada (Mbps)",
        "Antena",
        "Módem",
        "Costo mensual (USD)",
        "Estado",
    ]
    results = []
    for _, row in consultas.iterrows():
        municipio = str(row.get("municipio", "")).strip()
        capacidad_value = row.get("capacidad")
        try:
            capacidad = convertir_capacidad(capacidad_value)
        except (TypeError, ValueError):
            results.append({
                **{column: "" for column in result_columns},
                "Municipio": municipio,
                "Capacidad solicitada (Mbps)": capacidad_value,
                "Estado": "Error: capacidad inválida",
            })
            continue

        resultado = cotizar(municipio, capacidad)
        if resultado.get("error"):
            results.append({
                **{column: "" for column in result_columns},
                "Municipio": municipio,
                "Capacidad solicitada (Mbps)": capacidad,
                "Estado": resultado["error"],
            })
            continue

        results.append({
            "Municipio": resultado["municipio"],
            "Beam": resultado["beam"],
            "Satélite": resultado["satelite"],
            "Banda": resultado["banda"],
            "Plan": resultado["plan"],
            "Capacidad solicitada (Mbps)": resultado["capacidad"],
            "Antena": resultado["antena"],
            "Módem": resultado["modem"],
            "Costo mensual (USD)": resultado["costo_usd"],
            "Estado": "Cobertura y capacidad confirmadas",
        })

    archivo = BytesIO()
    with pd.ExcelWriter(archivo, engine="openpyxl") as writer:
        pd.DataFrame(results, columns=result_columns).to_excel(
            writer,
            index=False,
            sheet_name="Preofertas",
        )
    archivo.seek(0)

    return send_file(
        archivo,
        as_attachment=True,
        download_name="preofertas_sky_net.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# =========================================================
# AUTOCOMPLETADO DE MUNICIPIOS
# =========================================================

@app.route("/buscar_municipios")
@login_required
def buscar_municipios():

    query = request.args.get(
        "q",
        ""
    ).lower().strip()

    if not query:

        return jsonify([])

    if municipios.empty:

        return jsonify([])

    resultados = municipios[
        municipios["municipio"].map(normalizar_texto).str.contains(
            normalizar_texto(query),
            na=False,
            regex=False,
        )
    ].head(10)

    return jsonify(
        resultados["municipio"]
        .tolist()
    )


# =========================================================
# FUNCIÓN DE COTIZACIÓN
# =========================================================

def cotizar(
    municipio,
    capacidad
):

    if cobertura.empty:

        return {
            "error": "No existe información de cobertura"
        }

    fila = cobertura[
        cobertura["municipio"].map(normalizar_texto)
        == normalizar_texto(municipio)
    ]

    if fila.empty:

        return {
            "error": "No hay cobertura para este municipio"
        }

    fila = fila.iloc[0]

    if planes.empty:

        return {
            "error": "No existe información de planes"
        }

    planes_disponibles = planes[
        planes["capacidad"] >= capacidad
    ]

    if planes_disponibles.empty:

        return {
            "error": "No existe un plan disponible para esta capacidad"
        }

    plan = planes_disponibles.iloc[0]

    return {

        "municipio": municipio,

        "beam": fila["beam"],

        "satelite": fila["satelite"],

        "banda": fila["banda"],

        "plan": plan["nombre"],

        "antena": plan["antena"],

        "modem": plan["modem"],

        "capacidad": capacidad,

        "costo_usd": plan["precio_usd"]
    }


# =========================================================
# EJECUCIÓN
# =========================================================

if __name__ == "__main__":

    app.run(
        debug=True
    )