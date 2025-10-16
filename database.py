# database.py
import os
import sys
import hashlib
import sqlite3
from contextlib import contextmanager
from PySide6.QtSql import QSqlDatabase
from PySide6.QtWidgets import QMessageBox

DB_FILE = "farmacia.db"


# ---------- Utilerías ----------
def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@contextmanager
def sqlite_conn():
    """Conexión de conveniencia con foreign_keys activado y commits seguros."""
    conn = sqlite3.connect(DB_FILE)
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        yield conn
        conn.commit()
    finally:
        conn.close()


def _ensure_schema(conn: sqlite3.Connection):
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE Articulos (
        codigo VARCHAR(20) PRIMARY KEY,
        descripcion VARCHAR(120) NOT NULL,
        precio DECIMAL(10,2) NOT NULL,
        en_promocion BOOLEAN NOT NULL DEFAULT FALSE,
        puntos_requeridos INT NOT NULL DEFAULT 50
    );

    CREATE TABLE Almacen (
        codArticulo VARCHAR(20) PRIMARY KEY REFERENCES Articulos(codigo),
        existencia INT NOT NULL DEFAULT 0,
        ubicacion VARCHAR(30)
    );

    CREATE TABLE Compras (
        idCompra BIGINT PRIMARY KEY,
        fecha DATETIME NOT NULL
    );

    CREATE TABLE Detalle_Compra (
        idCompra BIGINT NOT NULL REFERENCES Compras(idCompra),
        renglon INT NOT NULL,
        codArticulo VARCHAR(20) NOT NULL REFERENCES Articulos(codigo),
        cantidad INT NOT NULL,
        costo_unitario DECIMAL(10,2) NOT NULL,
        PRIMARY KEY (idCompra, renglon)
    );

    CREATE TABLE Clientes (
        idCliente BIGINT PRIMARY KEY,
        nombre VARCHAR(120) NOT NULL,
        puntos INT NOT NULL DEFAULT 0
    );

    CREATE TABLE Ventas (
        folio BIGINT PRIMARY KEY,
        fecha DATETIME NOT NULL,
        idCliente BIGINT NOT NULL REFERENCES Clientes(idCliente),
        total DECIMAL(10,2) NOT NULL
    );

    CREATE TABLE Detalle_Venta (
        folio BIGINT NOT NULL REFERENCES Ventas(folio),
        renglon INT NOT NULL,
        codArticulo VARCHAR(20) NOT NULL REFERENCES Articulos(codigo),
        cantidad INT NOT NULL,
        precio_unitario DECIMAL(10,2) NOT NULL,
        es_promocion BOOLEAN NOT NULL DEFAULT FALSE,
        PRIMARY KEY (folio, renglon)
    );
    """)
    
    # Desde aquí el código es de la versión anterior, falta adaptarlo

    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_clientes_usuario  ON clientes(usuario);"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_vehiculos_cliente ON vehiculos(cliente_id);"
    )

    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_reps_vehiculo     ON reparaciones(matricula);"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_reps_usuario      ON reparaciones(mecanico);"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_reps_pieza        ON reparaciones(pieza);"
    )

    cur.executescript("""
    CREATE TRIGGER IF NOT EXISTS trg_reparacion_ai
    AFTER INSERT ON reparaciones
    BEGIN
        UPDATE piezas
        SET stock = stock - NEW.cantidad
        WHERE descripcion = NEW.pieza;
    END;

    CREATE TRIGGER IF NOT EXISTS trg_reparacion_au
    AFTER UPDATE OF cantidad ON reparaciones
    BEGIN
        UPDATE piezas
        SET stock = stock + (OLD.cantidad - NEW.cantidad)
        WHERE descripcion = OLD.pieza;
    END;

    CREATE TRIGGER IF NOT EXISTS trg_reparacion_ad
    AFTER DELETE ON reparaciones
    BEGIN
        UPDATE piezas
        SET stock = stock + OLD.cantidad
        WHERE descripcion = OLD.pieza;
    END;
    """)


def _seed_admin(conn: sqlite3.Connection):
    """TODO: revisar que este código sea compatible con el nuevo esquema."""
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM usuarios;")
    if cur.fetchone()[0] == 0:
        cur.execute(
            """
            INSERT INTO usuarios (nombre, apellido, usuario, password_hash, rol)
            VALUES (?,?,?,?,?)
        """,
            ("Admin", "Sistema", "admin", sha256("admin"), "admin"),
        )


def init_sqlite_file():
    """
    Crea el archivo SQLite y tablas si no existen; mete admin/admin si usuarios está vacío.
    De paso activa foreign_keys en cada conexión y aplica triggers.
    """
    first_time = not os.path.exists(DB_FILE)
    with sqlite_conn() as conn:
        _ensure_schema(conn)
        _seed_admin(conn)
    return first_time


def open_qt_db_or_die():
    """
    Abre la conexión Qt a SQLite y asegura foreign_keys activado.
    Nota: hay que ejecutar también el PRAGMA en la conexión de Qt.
    """
    db = QSqlDatabase.addDatabase("QSQLITE")
    db.setDatabaseName(DB_FILE)
    if not db.open():
        QMessageBox.critical(None, "Error BD", "No se pudo abrir la base de datos.")
        sys.exit(1)

    # Asegurar foreign_keys en la conexión Qt
    # Usamos un QSqlQuery implícito a través de db.exec si está disponible.
    try:
        db.exec("PRAGMA foreign_keys = ON;")
    except Exception:
        pass
    return db
