from __future__ import annotations
from PySide6.QtCore import Qt, QDate, Signal, QRegularExpression, QRect, QEvent
from PySide6.QtGui import QRegularExpressionValidator, QIntValidator, QDoubleValidator
from PySide6.QtSql import QSqlTableModel
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QStyledItemDelegate,
    QDateEdit,
    QStyleOptionButton,
    QApplication,
    QStyle,
)
from database import _hash_password

# ---------------- Delegates ----------------


class BoolDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        # Sin editor: usaremos click para alternar
        return None

    def paint(self, painter, option, index):
        # Lee el valor como 0/1 o True/False
        value = index.model().data(index, Qt.EditRole)
        is_checked = bool(value)

        # Prepara las opciones del checkbox
        opt = QStyleOptionButton()
        opt.state |= QStyle.State_Enabled
        opt.state |= QStyle.State_On if is_checked else QStyle.State_Off

        # Centra el checkbox en la celda
        opt.rect = self._checkbox_rect(option)

        # Dibuja
        QApplication.style().drawControl(QStyle.CE_CheckBox, opt, painter)

    def editorEvent(self, event, model, option, index):
        # Solo si es editable
        if not (index.flags() & Qt.ItemIsEditable):
            return False

        et = event.type()
        # Permite click y barra espaciadora/enter
        is_mouse = et in (QEvent.MouseButtonRelease, QEvent.MouseButtonDblClick)
        is_key = et == QEvent.KeyPress and event.key() in (
            Qt.Key_Space,
            Qt.Key_Return,
            Qt.Key_Enter,
        )

        if not (is_mouse or is_key):
            return False

        # Si fue doble click, evita que el doble click pase a otras cosas
        if et == QEvent.MouseButtonDblClick:
            return True

        # Alterna 0/1
        current = bool(model.data(index, Qt.EditRole))
        return model.setData(index, 0 if current else 1, Qt.EditRole)

    def _checkbox_rect(self, option):
        # Calcula el rectángulo del indicador nativo del checkbox
        opt = QStyleOptionButton()
        indicator = QApplication.style().subElementRect(
            QStyle.SE_CheckBoxIndicator, opt, None
        )
        x = option.rect.x() + (option.rect.width() - indicator.width()) // 2
        y = option.rect.y() + (option.rect.height() - indicator.height()) // 2
        return QRect(x, y, indicator.width(), indicator.height())


class PasswordDelegate(QStyledItemDelegate):
    """Muestra **** y, al editar, toma texto plano y guarda sha256 en el modelo."""

    def createEditor(self, parent, option, index):
        edit = QLineEdit(parent)
        edit.setEchoMode(QLineEdit.Password)
        return edit

    def setEditorData(self, editor, index):
        # Nunca mostramos el hash ni un pseudo valor; campo en blanco para escribir nuevo password
        editor.setText("")

    def setModelData(self, editor, model, index):
        pwd = editor.text()
        if not pwd:
            # Si el usuario no escribió nada, no tocamos el hash existente
            return
        model.setData(index, _hash_password(pwd))

    def displayText(self, value, locale):
        # En modo display siempre se ve **** si hay algo, o vacío si no hay hash
        return "****" if value else ""


class SmartDelegate(QStyledItemDelegate):
    """
    Delegate genérico:
    - Emite señales al iniciar/terminar edición.
    - Crea editores específicos por tipo de columna (fechas, enteros, reales, texto).
    - Valida antes de escribir en el modelo.
    """

    editingStarted = Signal(object)  # QModelIndex
    editingFinished = Signal(object, bool)  # QModelIndex, accepted

    def __init__(self, parent=None, table_name: str = "", header_lookup=None):
        super().__init__(parent)
        self.table_name = table_name
        # función para mapear índice->nombre de columna
        self.header_lookup = header_lookup or (lambda col: "")

    # -------- helpers de tipo/validación --------
    def _colname(self, index) -> str:
        return self.header_lookup(index.column())

    def _is_date_col(self, colname: str) -> bool:
        return "fecha" in colname.lower()

    def _is_fk_or_id(self, colname: str) -> bool:
        # id, cliente_id, idUsuario, idVehiculo, etc.
        cn = colname.lower()
        return cn == "id" or cn.startswith("id")

    def _is_int_nonneg(self, colname: str) -> bool:
        return colname in {"stock", "numero_piezas", "cantidad"} or self._is_fk_or_id(
            colname
        )

    def _is_real_nonneg(self, colname: str) -> bool:
        return colname == "precio"

    def _needs_email_validator(self, colname: str) -> bool:
        return colname.lower() in {"email", "correo"}

    def _needs_name_validator(self, colname: str) -> bool:
        return colname.lower() in {"nombre", "marca", "modelo"}

    # -------- fábrica de editores --------
    def createEditor(self, parent, option, index):
        self.editingStarted.emit(index)
        colname = self._colname(index)

        if self._is_date_col(colname):
            d = QDateEdit(parent)
            d.setCalendarPopup(True)
            d.setDisplayFormat("yyyy-MM-dd")
            return d

        # Numéricos
        if self._is_int_nonneg(colname):
            edit = QLineEdit(parent)
            v = QIntValidator(0, 2_147_483_647, edit)
            edit.setValidator(v)
            return edit

        if self._is_real_nonneg(colname):
            edit = QLineEdit(parent)
            v = QDoubleValidator(0.0, 1e12, 4, edit)
            v.setNotation(QDoubleValidator.StandardNotation)
            edit.setValidator(v)
            return edit

        # Texto con validadores suaves
        edit = QLineEdit(parent)
        if self._needs_email_validator(colname):
            rx = QRegularExpression(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
            edit.setValidator(QRegularExpressionValidator(rx, edit))
        elif self._needs_name_validator(colname):
            rx = QRegularExpression(r"^\S.*$")
            edit.setValidator(QRegularExpressionValidator(rx, edit))
        return edit

    def setEditorData(self, editor, index):
        # colname = self._colname(index)

        if isinstance(editor, QDateEdit):
            raw = index.data(Qt.EditRole) or index.data(Qt.DisplayRole)
            # raw puede ser "YYYY-MM-DD" o vacío
            qd = QDate.fromString(str(raw) if raw else "", "yyyy-MM-dd")
            if not qd.isValid():
                qd = QDate.currentDate()
            editor.setDate(qd)
            return

        # Para QLineEdit: carga texto sin None
        editor.setText(
            "" if index.data(Qt.EditRole) is None else str(index.data(Qt.EditRole))
        )

    def setModelData(self, editor, model, index):
        colname = self._colname(index)

        # Fecha: no futura y coherencia en reparaciones (entrada <= salida)
        if isinstance(editor, QDateEdit):
            date = editor.date()
            if not date.isValid() or date > QDate.currentDate().addDays(1):
                QMessageBox.warning(
                    editor,
                    "Fecha inválida",
                    "Introduce una fecha válida que no sea futura.",
                )
                self.editingFinished.emit(index, False)
                return

            # validación cruzada en tabla reparaciones
            if self.table_name == "reparaciones":
                # revisa la otra fecha si existe
                row = index.row()
                model_rec = model.record(row)

                def get_date_str(fname: str):
                    fidx = model_rec.indexOf(fname)
                    if fidx == -1:
                        return ""
                    return str(model.data(model.index(row, fidx), Qt.EditRole) or "")

                if colname == "fechaEntrada":
                    salida = QDate.fromString(get_date_str("fechaSalida"), "yyyy-MM-dd")
                    if salida.isValid() and date > salida:
                        QMessageBox.warning(
                            editor,
                            "Rango de fechas",
                            "fechaEntrada no puede ser posterior a fechaSalida.",
                        )
                        self.editingFinished.emit(index, False)
                        return
                elif colname == "fechaSalida":
                    entrada = QDate.fromString(
                        get_date_str("fechaEntrada"), "yyyy-MM-dd"
                    )
                    if entrada.isValid() and date < entrada:
                        QMessageBox.warning(
                            editor,
                            "Rango de fechas",
                            "fechaSalida no puede ser anterior a fechaEntrada.",
                        )
                        self.editingFinished.emit(index, False)
                        return

            model.setData(index, date.toString("yyyy-MM-dd"), Qt.EditRole)
            self.editingFinished.emit(index, True)
            return

        # QLineEdit con validator
        if isinstance(editor, QLineEdit):
            if editor.validator():
                # Qt valida en tiempo real, pero verificamos por si acaso
                state = editor.validator().validate(editor.text(), 0)[0]
                if (
                    state != QRegularExpressionValidator.Acceptable
                    and not isinstance(editor.validator(), QIntValidator)
                    and not isinstance(editor.validator(), QDoubleValidator)
                ):
                    QMessageBox.warning(
                        editor, "Valor inválido", "Corrige el campo antes de guardar."
                    )
                    self.editingFinished.emit(index, False)
                    return
            # Para int/real, si está vacío y es requerido, bloquea
            if self._is_int_nonneg(colname) or self._is_real_nonneg(colname):
                txt = editor.text().strip()
                if txt == "":
                    QMessageBox.warning(
                        editor, "Campo requerido", f"{colname} no puede estar vacío."
                    )
                    self.editingFinished.emit(index, False)
                    return

            model.setData(index, editor.text(), Qt.EditRole)
            self.editingFinished.emit(index, True)
            return

    # Puedes ajustar geometría si lo necesitas:
    # def updateEditorGeometry(self, editor, option, index):
    #     editor.setGeometry(option.rect)


# ---------------- Dialog ----------------


class CrudDialog(QDialog):
    def __init__(
        self,
        table: str,
        title: str,
        editable_columns: list[str] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(800, 480)
        self.table = table
        self.model = QSqlTableModel(self)
        self.model.setTable(table)
        self.model.setEditStrategy(QSqlTableModel.OnManualSubmit)
        self.model.select()

        self.view = QTableView()
        self.view.setModel(self.model)
        self.view.setSelectionBehavior(QTableView.SelectRows)
        self.view.setSelectionMode(QTableView.SingleSelection)
        self.view.setAlternatingRowColors(True)

        # Delegate genérico para todo
        smart = SmartDelegate(
            self.view, table_name=self.table, header_lookup=self._column_name_by_index
        )
        self.view.setItemDelegate(smart)

        # Tap para saber cuándo inicia/termina edición
        smart.editingStarted.connect(self._on_edit_start)
        smart.editingFinished.connect(self._on_edit_finish)

        if table == "Articulos":
            col = self._column_index("en_promocion")
            if col != -1:
                self.view.setItemDelegateForColumn(col, BoolDelegate(self.view))

        # Delegate específico para password_hash si aplica
        if table == "Usuarios":
            idx = self._column_index("password_hash")
            if idx != -1:
                self.view.setItemDelegateForColumn(idx, PasswordDelegate(self))
                self.model.setHeaderData(idx, Qt.Horizontal, "password")
            ridx = self._column_index("rol")
            if ridx != -1:
                self.model.setHeaderData(ridx, Qt.Horizontal, "rol")

        # Filtro rápido
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText(
            "Filtrar (SQL LIKE sobre todas las columnas visibles)..."
        )
        self.filter_edit.textChanged.connect(self.apply_filter)

        # Botones
        self.btn_add = QPushButton("Nuevo")
        self.btn_del = QPushButton("Eliminar")
        self.btn_save = QPushButton("Guardar")
        self.btn_revert = QPushButton("Revertir")

        self.btn_add.clicked.connect(self.add_row)
        self.btn_del.clicked.connect(self.del_row)
        self.btn_save.clicked.connect(self.save_changes)
        self.btn_revert.clicked.connect(self.model.revertAll)

        # Layout
        top = QHBoxLayout()
        top.addWidget(QLabel("Buscar:"))
        top.addWidget(self.filter_edit)

        btns = QHBoxLayout()
        for b in (self.btn_add, self.btn_del, self.btn_save, self.btn_revert):
            btns.addWidget(b)
        btns.addStretch()

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.view)
        layout.addLayout(btns)

    # -------- utilidades de columnas --------
    def _column_index(self, name: str) -> int:
        rec = self.model.record()
        for i in range(rec.count()):
            if rec.fieldName(i) == name:
                return i
        return -1

    def _column_name_by_index(self, i: int) -> str:
        return self.model.record().fieldName(i)

    def hide_column_by_name(self, name: str):
        idx = self._column_index(name)
        if idx != -1:
            self.view.setColumnHidden(idx, True)

    # -------- CRUD actions --------
    def add_row(self):
        row = self.model.rowCount()
        self.model.insertRow(row)
        # Dejar que SQLite lo genere automáticamente; no tocar el id
        id_idx = self._column_index("id")
        if id_idx != -1:
            self.model.setData(self.model.index(row, id_idx), None)

    def del_row(self):
        idx = self.view.currentIndex()
        if not idx.isValid():
            return
        self.model.removeRow(idx.row())

    def save_changes(self):
        # Nota: las restricciones de tu esquema (FK, CHECK, UNIQUE) también pueden fallar aquí.
        # Si explota, mostramos el error de Qt.
        if not self.model.submitAll():
            err = self.model.lastError()
            msg = getattr(err, "text", lambda: str(err))()
            QMessageBox.critical(self, "Error", f"No se pudo guardar:\n{msg}")
        else:
            self.model.select()

    def apply_filter(self, text: str):
        text = text.strip()
        if not text:
            self.model.setFilter("")
            self.model.select()
            return

        esc = text.replace("'", "''")
        rec = self.model.record()
        likes = []
        for i in range(rec.count()):
            if self.view.isColumnHidden(i):
                continue
            col = rec.fieldName(i)
            likes.append(f"CAST(\"{col}\" AS TEXT) LIKE '%{esc}%'")
        self.model.setFilter(" OR ".join(likes))
        self.model.select()

    # -------- hooks de edición (debug/log/lo que quieras) --------
    def _on_edit_start(self, index):
        # Aquí sabes que se abrió un editor; útil para marcar "fila en edición"
        # print(f"[edit] start row={index.row()} col={index.column()} {self._column_name_by_index(index.column())}")
        pass

    def _on_edit_finish(self, index, accepted: bool):
        # Se cerró editor; accepted indica si pasó validación y se escribió en el modelo.
        # print(f"[edit] done  row={index.row()} col={index.column()} ok={accepted}")
        pass
