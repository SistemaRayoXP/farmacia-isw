from __future__ import annotations
from views.CrudDialog import CrudDialog
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QMessageBox,
    QToolBar,
)

class MainWindow(QMainWindow):
    logout_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Farmacia - Mini POS")
        self.resize(400, 300)
        self._build_menus()

        tb = QToolBar("Acciones", self)
        self.addToolBar(tb)
        tb.addAction("Clientes", lambda: self.open_crud("Clientes", "Clientes"))
        tb.addAction("Ventas",   lambda: self.open_crud("Ventas", "Ventas"))
        tb.addAction("Artículos",lambda: self.open_crud("Articulos", "Artículos"))

        self.setCentralWidget(QLabel("Listo. Usa el menú para abrir un CRUD.",alignment=Qt.AlignmentFlag.AlignCenter))

    def _build_menus(self):
        m_cat = self.menuBar().addMenu("&Catálogo")
        self.add_catalog_action(m_cat, "Artículos", "Articulos")
        self.add_catalog_action(m_cat, "Almacén", "Almacen")
        self.add_catalog_action(m_cat, "Clientes", "Clientes")

        m_mov = self.menuBar().addMenu("&Movimientos")
        self.add_catalog_action(m_mov, "Compras", "Compras")
        self.add_catalog_action(m_mov, "Detalle de compras", "Detalle_Compra")
        self.add_catalog_action(m_mov, "Ventas", "Ventas")
        self.add_catalog_action(m_mov, "Detalle de ventas", "Detalle_Venta")

        m_seg = self.menuBar().addMenu("&Seguridad")
        self.add_catalog_action(m_seg, "Usuarios", "Usuarios")

        m_help = self.menuBar().addMenu("Ay&uda")
        about = QAction("Acerca de…", self)
        about.triggered.connect(lambda: QMessageBox.information(self, "Farmacia", "Mini farmacia con puntos y promos."))
        m_help.addAction(about)

    def add_catalog_action(self, menu, text, table):
        act = QAction(text, self)
        act.triggered.connect(lambda: self.open_crud(table, text))
        menu.addAction(act)

    def open_crud(self, table: str, label: str):
        dlg = CrudDialog(table, f"{label} - CRUD", parent=self)
        dlg.exec()

    def request_logout(self):
        if QMessageBox.question(self, "Cerrar sesión", "¿Volver a la pantalla de login?") == QMessageBox.Yes:
            self.logout_requested.emit()
            self.close()
