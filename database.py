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
def _hash_password(text: str) -> str:
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
    cur.executescript("""
    PRAGMA foreign_keys=ON;

    -- Seguridad
    CREATE TABLE IF NOT EXISTS Usuarios (
        usuario_id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        correo TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        rol TEXT NOT NULL
    );
    
    CREATE TABLE IF NOT EXISTS Clientes (
      cliente_id INTEGER PRIMARY KEY,
      usuario_id INTEGER NOT NULL REFERENCES Usuarios(usuario_id) ON DELETE RESTRICT,
      nombre VARCHAR(120) NOT NULL,
      rfc TEXT,
      direccion TEXT,
      telefono BIGINT,
      puntos INT NOT NULL DEFAULT 0 CHECK (puntos >= 0)
    );
    
    CREATE TABLE IF NOT EXISTS Ventas (
      folio INTEGER PRIMARY KEY,
      fecha DATETIME NOT NULL,
      cliente_id INTEGER NOT NULL REFERENCES Clientes(cliente_id),
      usuario_id INTEGER NOT NULL REFERENCES Usuarios(usuario_id),
      total DECIMAL(10,2) NOT NULL CHECK (total >= 0)
    );

    CREATE TABLE IF NOT EXISTS Detalle_Venta (
      folio_venta INTEGER NOT NULL REFERENCES Ventas(folio) ON DELETE CASCADE,
      detalle_venta_id INT NOT NULL,
      codigo_articulo VARCHAR(20) NOT NULL REFERENCES Articulos(codigo),
      cantidad INT NOT NULL CHECK (cantidad > 0),
      precio_unitario DECIMAL(10,2) NOT NULL CHECK (precio_unitario >= 0),
      PRIMARY KEY (folio_venta, detalle_venta_id)
    );

    CREATE TABLE IF NOT EXISTS Articulos (
      codigo VARCHAR(20) PRIMARY KEY,
      descripcion VARCHAR(120) NOT NULL,
      precio DECIMAL(10,2) NOT NULL,
      en_promocion BOOLEAN NOT NULL DEFAULT FALSE
    );

    CREATE TABLE IF NOT EXISTS Almacen (
      codigo_articulo VARCHAR(20) PRIMARY KEY REFERENCES Articulos(codigo) ON DELETE CASCADE,
      existencia INT NOT NULL DEFAULT 0,
      ubicacion VARCHAR(30)
    );

    CREATE TABLE IF NOT EXISTS Compras (
      compra_id INTEGER PRIMARY KEY,
      fecha DATETIME NOT NULL
    );

    CREATE TABLE IF NOT EXISTS Detalle_Compra (
      compra_id INTEGER NOT NULL REFERENCES Compras(compra_id) ON DELETE CASCADE,
      detalle_compra_id INT NOT NULL,
      codigo_articulo VARCHAR(20) NOT NULL REFERENCES Articulos(codigo),
      cantidad INT NOT NULL CHECK (cantidad >= 0),
      costo_unitario DECIMAL(10,2) NOT NULL CHECK (costo_unitario >= 0),
      PRIMARY KEY (compra_id, detalle_compra_id)
    );

    -- Asegura fila en almacén al crear artículo
    CREATE TRIGGER IF NOT EXISTS trg_articulo_ai
    AFTER INSERT ON Articulos
    BEGIN
      INSERT OR IGNORE INTO Almacen(codigo_articulo, existencia) VALUES (NEW.codigo, 0);
    END;

    -- Compras: sube stock
    CREATE TRIGGER IF NOT EXISTS trg_detcompra_ai
    AFTER INSERT ON Detalle_Compra
    BEGIN
      UPDATE Almacen SET existencia = existencia + NEW.cantidad
      WHERE codigo_articulo = NEW.codigo_articulo;
    END;

    CREATE TRIGGER IF NOT EXISTS trg_detcompra_au
    AFTER UPDATE OF cantidad, codigo_articulo ON Detalle_Compra
    BEGIN
      UPDATE Almacen SET existencia = existencia - OLD.cantidad WHERE codigo_articulo = OLD.codigo_articulo;
      UPDATE Almacen SET existencia = existencia + NEW.cantidad WHERE codigo_articulo = NEW.codigo_articulo;
    END;

    CREATE TRIGGER IF NOT EXISTS trg_detcompra_ad
    AFTER DELETE ON Detalle_Compra
    BEGIN
      UPDATE Almacen SET existencia = existencia - OLD.cantidad
      WHERE codigo_articulo = OLD.codigo_articulo;
    END;

    -- Ventas: baja stock
    CREATE TRIGGER IF NOT EXISTS trg_detventa_ai
    AFTER INSERT ON Detalle_Venta
    BEGIN
      UPDATE Almacen SET existencia = existencia - NEW.cantidad
      WHERE codigo_articulo = NEW.codigo_articulo;
    END;

    CREATE TRIGGER IF NOT EXISTS trg_detventa_au
    AFTER UPDATE OF cantidad, codigo_articulo ON Detalle_Venta
    BEGIN
      UPDATE Almacen SET existencia = existencia + OLD.cantidad WHERE codigo_articulo = OLD.codigo_articulo;
      UPDATE Almacen SET existencia = existencia - NEW.cantidad WHERE codigo_articulo = NEW.codigo_articulo;
    END;

    CREATE TRIGGER IF NOT EXISTS trg_detventa_ad
    AFTER DELETE ON Detalle_Venta
    BEGIN
      UPDATE Almacen SET existencia = existencia + OLD.cantidad
      WHERE codigo_articulo = OLD.codigo_articulo;
    END;

    -- Puntos: 4 por cada $100 ENTEROS del total
    CREATE TRIGGER IF NOT EXISTS trg_venta_ai_points
    AFTER INSERT ON Ventas
    BEGIN
      UPDATE Clientes
      SET puntos = puntos + ((CAST(NEW.total AS INTEGER) / 100) * 4)
      WHERE cliente_id = NEW.cliente_id;
    END;
    """)


def seed_user(
    conn: sqlite3.Connection,
    correo: str = "admin@farmacia.cucei.udg.mx",
    password_plano: str = "admin",
    nombre: str = "Admin Sistema",
    rol: str = "admin",
) -> int:
    """
    Crea/actualiza un usuario admin. Idempotente.
    Devuelve usuario_id del admin.
    """
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys=ON")

    # Asegura tabla Usuarios exista
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='Usuarios'")
    if not cur.fetchone():
        return 0  # esquema no creado todavía

    # Busca si existe
    cur.execute("SELECT usuario_id FROM Usuarios WHERE correo = ?", (correo,))
    row = cur.fetchone()
    pwd_hash = _hash_password(password_plano)

    if row is None:
        # Inserta
        cur.execute(
            """
            INSERT INTO Usuarios (nombre, correo, password_hash, rol)
            VALUES (?,?,?,?)
            """,
            (nombre, correo, pwd_hash, rol),
        )
        user_id = cur.lastrowid

    conn.commit()
    return user_id


def seed_minima(conn: sqlite3.Connection, user_id: int | None = None) -> None:
    """
    Inserta artículos base, un par de clientes, y una compra demo para stock.
    Respeta FKs: requiere un usuario existente y lo usa como dueño de clientes.
    """
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys=ON")

    # Asegura user_id válido para Clientes.usuario_id
    if not user_id:
        cur.execute("SELECT usuario_id FROM Usuarios ORDER BY usuario_id LIMIT 1")
        row = cur.fetchone()
        if row is None:
            # No hay usuarios; sin eso no se puede poblar Clientes
            conn.commit()
            return
        user_id = row[0]

    # Artículos base
    cur.execute("SELECT 1 FROM Articulos LIMIT 1")
    if cur.fetchone() is None:
        articulos = [
            ("PARA500", "Paracetamol 500 mg 10 tabs", 35.00, 1),
            ("IBU400", "Ibuprofeno 400 mg 10 tabs", 42.00, 0),
            ("JARGRIP", "Jarabe para la gripe 120 ml", 79.00, 1),
            ("VITC1G", "Vitamina C 1 g 10 tabs", 55.00, 0),
        ]
        cur.executemany(
            """
            INSERT OR IGNORE INTO Articulos(codigo, descripcion, precio, en_promocion)
            VALUES (?,?,?,?)
            """,
            articulos,
        )
        # Almacén se crea vía trigger al insertar Articulos

    # Clientes base (ahora con usuario_id)
    cur.execute("SELECT cliente_id FROM Clientes LIMIT 1")
    cliente = cur.fetchone()
    if cliente is None:
        clientes = [
            (1, "Público General", 0),
            (2, "Edson Armando", 0),
        ]
        for cid, nombre, pts in clientes:
            cur.execute(
                """
                INSERT OR IGNORE INTO Clientes(cliente_id, usuario_id, nombre, puntos)
                VALUES (?,?,?,?)
                """,
                (cid, user_id, nombre, pts),
            )
        cur.execute("SELECT cliente_id FROM Clientes LIMIT 1")
        cliente_id = cur.fetchone()[0]
    else:
        cliente_id = cliente[0]

    # Compra demo para subir stock
    cur.execute("SELECT 1 FROM Compras LIMIT 1")
    if cur.fetchone() is None:
        cur.execute(
            "INSERT INTO Compras(compra_id, fecha) VALUES (?, datetime('now'))", (1,)
        )
        detalle = [
            (1, 1, "PARA500", 30, 18.50),
            (1, 2, "IBU400", 20, 22.00),
            (1, 3, "JARGRIP", 15, 45.00),
            (1, 4, "VITC1G", 25, 28.00),
        ]
        cur.executemany(
            """
            INSERT OR IGNORE INTO Detalle_Compra(
              compra_id, detalle_compra_id, codigo_articulo, cantidad, costo_unitario
            ) VALUES (?,?,?,?,?)
            """,
            detalle,
        )

    conn.commit()
    
    return cliente_id  # devuelve el ID del cliente recién creado


def seed_venta_demo(conn: sqlite3.Connection, cliente_id: int) -> None:
    """
    Inserta una venta demo folio 1001 con detalles coherentes.
    Requiere que existan Clientes(2) y un usuario válido.
    """
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys=ON")

    # Determina usuario_id para la venta
    cur.execute("SELECT usuario_id FROM Usuarios ORDER BY usuario_id LIMIT 1")
    row = cur.fetchone()
    if row is None:
        return
    usuario_id = row[0]

    # Verifica que el cliente existe otro caso no hace nada
    cur.execute("SELECT 1 FROM Clientes WHERE cliente_id = ?", (cliente_id,))
    if cur.fetchone() is None:
        conn.commit()
        return

    # Venta
    cur.execute("SELECT 1 FROM Ventas WHERE folio = 1001")
    if cur.fetchone() is None:
        cur.execute(
            """
            INSERT INTO Ventas(folio, fecha, cliente_id, usuario_id, total)
            VALUES (?, datetime('now'), ?, ?, ?)
            """,
            (1001, cliente_id, usuario_id, 300.00),
        )

    # Detalle
    cur.execute("SELECT 1 FROM Detalle_Venta WHERE folio_venta = 1001")
    if cur.fetchone() is None:
        cur.executemany(
            """
            INSERT INTO Detalle_Venta(
              folio_venta, detalle_venta_id, codigo_articulo, cantidad, precio_unitario
            ) VALUES (?,?,?,?,?)
            """,
            [
                (1001, 1, "PARA500", 2, 35.00),
                (1001, 2, "IBU400", 1, 42.00),
                (1001, 3, "JARGRIP", 1, 0.00),
            ],
        )
        # Si quieres “canjear 50 puntos”
        cur.execute(
            """
            UPDATE Clientes
            SET puntos = CASE WHEN puntos >= 50 THEN puntos - 50 ELSE puntos END
            WHERE cliente_id = 2
            """
        )

    conn.commit()


def init_sqlite_file():
    """
    Crea el archivo SQLite y tablas si no existen; mete admin/admin si usuarios está vacío.
    De paso activa foreign_keys en cada conexión y aplica triggers.
    """
    first_time = not os.path.exists(DB_FILE)
    with sqlite_conn() as conn:
        _ensure_schema(conn)
        seed_user(conn)  # crea/actualiza admin y COMMIT
        cajero_id = seed_user(conn, "luis@farmacia.cucei.udg.mx", "luis", "Luis Perez", "cajero")  # crea/actualiza cajero y COMMIT
        cliente_id = seed_minima(conn, cajero_id)  # usa admin_id para Clientes.usuario_id
        seed_venta_demo(conn, cliente_id)  # crea venta y detalles si faltan

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
