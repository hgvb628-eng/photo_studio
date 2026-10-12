"""Главное окно приложения «Фотостудия»."""
import queue
import re
import threading
import tkinter as tk
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Optional, Sequence

import pandas as pd
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

import db
from auth import User
from config import (ROLE_ADMIN, ROLE_CLIENT, ROLE_PHOTOGRAPHER,
                    STATUS_CANCELLED, STATUS_DONE, STATUS_PLANNED)

# ============= ТЕМЫ =============
LIGHT = {"bg": "#f0f0f0", "fg": "#2c3e50", "panel": "#ffffff", "bar": "#dfe4ea",
         "accent": "#3498db", "accent_dark": "#2980b9", "row_even": "#f8f9fa",
         "row_odd": "#ffffff", "error": "#e74c3c"}
DARK = {"bg": "#2c3e50", "fg": "#ecf0f1", "panel": "#34495e", "bar": "#22303d",
        "accent": "#2980b9", "accent_dark": "#3498db", "row_even": "#3b5268",
        "row_odd": "#34495e", "error": "#ff7675"}

READY_TEXT = "✅ Готов к работе"


# ============= ОПИСАНИЕ ТАБЛИЦ =============
@dataclass(frozen=True)
class EditCol:
    """Поле, которое можно менять двойным щелчком по записи."""
    column: str          # колонка в БД
    label: str           # подпись в форме
    idx: int             # номер столбца в выбранной строке
    choices: tuple = ()  # если задано, поле будет выпадающим списком
    required: bool = True


@dataclass(frozen=True)
class TableSpec:
    key: str
    title: str
    query: str
    headers: tuple
    param: Optional[str] = None      # "client_id" или "photographer_id" для личных таблиц
    table: Optional[str] = None      # таблица для UPDATE/DELETE (только у администратора)
    id_column: Optional[str] = None
    editable: tuple = ()


CLIENTS = TableSpec(
    "clients", "👥 Клиенты",
    "SELECT id_клиента, ФИО, Телефон, email, дата_регистрации FROM клиент",
    ("ID", "ФИО", "Телефон", "Email", "Дата регистрации"),
    table="клиент", id_column="id_клиента",
    editable=(EditCol("ФИО", "ФИО", 1), EditCol("Телефон", "Телефон", 2),
              EditCol("email", "Email", 3)))

PHOTOGRAPHERS = TableSpec(
    "photographers", "📸 Фотографы",
    "SELECT id_фотографа, ФИО, специализация, Телефон, опыт, Рейтинг, стоимость_час FROM фотограф",
    ("ID", "ФИО", "Специализация", "Телефон", "Опыт", "Рейтинг", "Цена/час"),
    table="фотограф", id_column="id_фотографа",
    editable=(EditCol("ФИО", "ФИО", 1), EditCol("специализация", "Специализация", 2),
              EditCol("Телефон", "Телефон", 3), EditCol("опыт", "Опыт", 4),
              EditCol("Рейтинг", "Рейтинг", 5), EditCol("стоимость_час", "Цена/час", 6)))

SERVICES = TableSpec(
    "services", "✨ Услуги",
    "SELECT id_услуги, название, тип, длительность, стоимость, описание FROM услуга",
    ("ID", "Название", "Тип", "Длит(ч)", "Стоимость", "Описание"),
    table="услуга", id_column="id_услуги",
    editable=(EditCol("название", "Название", 1), EditCol("тип", "Тип", 2),
              EditCol("длительность", "Длительность (ч)", 3),
              EditCol("стоимость", "Стоимость", 4),
              EditCol("описание", "Описание", 5, required=False)))

LOCATIONS = TableSpec(
    "locations", "📍 Локации",
    "SELECT id_локации, название, адрес, город, цена_час, график_работы FROM локация",
    ("ID", "Название", "Адрес", "Город", "Цена/час", "График работы"),
    table="локация", id_column="id_локации",
    editable=(EditCol("название", "Название", 1), EditCol("адрес", "Адрес", 2),
              EditCol("город", "Город", 3), EditCol("цена_час", "Цена/час", 4),
              EditCol("график_работы", "График работы", 5, required=False)))

EQUIPMENT = TableSpec(
    "equipment", "🛠️ Оборудование",
    "SELECT id_оборудования, название, тип, инвентарный_номер, статус FROM оборудование",
    ("ID", "Название", "Тип", "Инв.номер", "Статус"),
    table="оборудование", id_column="id_оборудования",
    editable=(EditCol("название", "Название", 1), EditCol("тип", "Тип", 2),
              EditCol("инвентарный_номер", "Инвентарный номер", 3),
              EditCol("статус", "Статус", 4)))

SESSIONS_ADMIN = TableSpec(
    "sessions", "📅 Фотосессии",
    """SELECT с.id_сессии, к.ФИО, ф.ФИО, у.название, л.название,
              с.дата, с.время, с.длительность, с.сумма, с.статус
       FROM фотосессия с
       JOIN клиент к ON с.id_клиента = к.id_клиента
       JOIN фотограф ф ON с.id_фотографа = ф.id_фотографа
       JOIN услуга у ON с.id_услуги = у.id_услуги
       LEFT JOIN локация л ON с.id_локации = л.id_локации""",
    ("ID", "Клиент", "Фотограф", "Услуга", "Локация", "Дата", "Время", "Длит", "Сумма", "Статус"),
    table="фотосессия", id_column="id_сессии",
    editable=(EditCol("статус", "Статус", 9,
                      choices=(STATUS_PLANNED, STATUS_DONE, STATUS_CANCELLED)),))

REVIEWS_ADMIN = TableSpec(
    "reviews", "💬 Отзывы",
    """SELECT о.id_отзыва, к.ФИО, ф.ФИО, о.оценка, о.текст_отзыва, о.дата_отзыва
       FROM отзыв о
       JOIN фотосессия с ON о.id_сессии = с.id_сессии
       JOIN клиент к ON с.id_клиента = к.id_клиента
       JOIN фотограф ф ON с.id_фотографа = ф.id_фотографа""",
    ("ID", "Клиент", "Фотограф", "Оценка", "Отзыв", "Дата"),
    table="отзыв", id_column="id_отзыва")

MY_SESSIONS = TableSpec(
    "my_sessions", "📅 Мои фотосессии",
    """SELECT с.id_сессии, у.название, л.название, ф.ФИО,
              с.дата, с.время, с.длительность, с.сумма, с.статус
       FROM фотосессия с
       JOIN услуга у ON с.id_услуги = у.id_услуги
       LEFT JOIN локация л ON с.id_локации = л.id_локации
       JOIN фотограф ф ON с.id_фотографа = ф.id_фотографа
       WHERE с.id_клиента = %s""",
    ("ID", "Услуга", "Локация", "Фотограф", "Дата", "Время", "Длит", "Сумма", "Статус"),
    param="client_id")

MY_REVIEWS = TableSpec(
    "my_reviews", "💬 Мои отзывы",
    """SELECT о.id_отзыва, ф.ФИО, о.оценка, о.текст_отзыва, о.дата_отзыва
       FROM отзыв о
       JOIN фотосессия с ON о.id_сессии = с.id_сессии
       JOIN фотограф ф ON с.id_фотографа = ф.id_фотографа
       WHERE с.id_клиента = %s""",
    ("ID", "Фотограф", "Оценка", "Отзыв", "Дата"),
    param="client_id")

PH_SESSIONS = TableSpec(
    "ph_sessions", "📅 Мои съёмки",
    """SELECT с.id_сессии, к.ФИО, у.название, л.название,
              с.дата, с.время, с.длительность, с.сумма, с.статус
       FROM фотосессия с
       JOIN клиент к ON с.id_клиента = к.id_клиента
       JOIN услуга у ON с.id_услуги = у.id_услуги
       LEFT JOIN локация л ON с.id_локации = л.id_локации
       WHERE с.id_фотографа = %s""",
    ("ID", "Клиент", "Услуга", "Локация", "Дата", "Время", "Длит", "Сумма", "Статус"),
    param="photographer_id")

PH_REVIEWS = TableSpec(
    "ph_reviews", "💬 Отзывы обо мне",
    """SELECT о.id_отзыва, к.ФИО, о.оценка, о.текст_отзыва, о.дата_отзыва
       FROM отзыв о
       JOIN фотосессия с ON о.id_сессии = с.id_сессии
       JOIN клиент к ON с.id_клиента = к.id_клиента
       WHERE с.id_фотографа = %s""",
    ("ID", "Клиент", "Оценка", "Отзыв", "Дата"),
    param="photographer_id")


def readonly(spec: TableSpec) -> TableSpec:
    """Копия таблицы без прав на правку и удаление (для клиента и фотографа)."""
    return replace(spec, table=None, id_column=None, editable=())


def specs_for(role: str) -> list:
    if role == ROLE_ADMIN:
        return [CLIENTS, PHOTOGRAPHERS, SERVICES, LOCATIONS, EQUIPMENT,
                SESSIONS_ADMIN, REVIEWS_ADMIN]
    if role == ROLE_CLIENT:
        return [MY_SESSIONS, readonly(SERVICES), readonly(LOCATIONS), MY_REVIEWS]
    if role == ROLE_PHOTOGRAPHER:
        return [PH_SESSIONS, readonly(SERVICES), readonly(LOCATIONS), PH_REVIEWS]
    return []


# ============= ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =============
def fmt(value) -> str:
    """Человекочитаемое значение ячейки."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y %H:%M")
    if isinstance(value, date):
        return value.strftime("%d.%m.%Y")
    if isinstance(value, timedelta):
        total = int(value.total_seconds())
        return f"{total // 3600:02d}:{total % 3600 // 60:02d}"
    if isinstance(value, Decimal):
        return str(int(value)) if value == value.to_integral_value() else f"{value:.2f}"
    return str(value)


def check_phone(value: str) -> Optional[str]:
    return None if len(re.sub(r"\D", "", value)) >= 10 else "Телефон: минимум 10 цифр"


def check_email(value: str) -> Optional[str]:
    return None if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value) else "Некорректный email"


def check_date(value: str) -> Optional[str]:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return "Дата в формате ГГГГ-ММ-ДД, например 2026-10-25"
    return None


def check_time(value: str) -> Optional[str]:
    try:
        datetime.strptime(value, "%H:%M")
    except ValueError:
        return "Время в формате ЧЧ:ММ, например 14:30"
    return None


def check_positive(value: str) -> Optional[str]:
    try:
        return None if float(value.replace(",", ".")) > 0 else "Число должно быть больше нуля"
    except ValueError:
        return "Введите число"


@dataclass
class Field:
    """Поле универсальной формы ввода."""
    name: str
    label: str
    kind: str = "entry"            # entry | combo | text
    choices: Sequence[str] = ()
    initial: str = ""
    required: bool = True
    validator: Optional[Callable[[str], Optional[str]]] = None


MONTHLY_SQL = (
    "SELECT DATE_FORMAT(дата, '%%Y-%%m') AS месяц, COUNT(*) AS сессий, "
    "COALESCE(SUM(сумма), 0) AS итого FROM фотосессия "
    "WHERE {column} = %s AND статус = %s GROUP BY месяц ORDER BY месяц DESC"
)


# ============= ГЛАВНОЕ ПРИЛОЖЕНИЕ =============
class PhotoStudioApp:
    POLL_MS = 80
    SHORTCUTS = ("<Control-t>", "<Control-e>", "<Control-g>", "<Control-f>", "<F5>")

    def __init__(self, root: tk.Tk, user: User, on_logout: Callable[[], None]):
        self.root = root
        self.user = user
        self.on_logout = on_logout
        self.dark = False
        self.palette = LIGHT
        self.specs = specs_for(user.role)
        self.specs_by_key = {s.key: s for s in self.specs}

        self.notebook: Optional[ttk.Notebook] = None
        self.trees = {}
        self.search_vars = {}
        self.search_entries = {}
        self._rows = {}       # key -> список строк из БД
        self._sort = {}       # key -> (номер столбца, по убыванию?)
        self._loading = set()

        self._queue: queue.Queue = queue.Queue()
        self._pending = 0
        self._status_job = None
        self._poll_job = None

        root.title(f"📸 Фотостудия | {user.role}: {user.name}")
        root.geometry("1280x760")
        root.minsize(900, 520)

        self.style = ttk.Style()
        self.style.theme_use("clam")
        self.apply_theme()

        self._build_status_bar()
        self.progress = ttk.Progressbar(root, mode="indeterminate")
        self.progress.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=5)
        self._build_menu()

        if self.specs:
            self._build_tabs()
        else:
            ttk.Label(root, text=f"Для роли «{user.role}» нет доступных разделов.",
                      font=("Arial", 13)).pack(expand=True)

        self._bind_shortcuts()
        self._poll()
        if self.specs:
            self.load(self.specs[0].key)

    # ---------- жизненный цикл ----------
    def shutdown(self) -> None:
        """Отменить таймеры и горячие клавиши (перед выходом или сменой пользователя)."""
        for job in (self._status_job, self._poll_job):
            if job is not None:
                try:
                    self.root.after_cancel(job)
                except tk.TclError:
                    pass
        self._status_job = self._poll_job = None
        for sequence in self.SHORTCUTS:
            try:
                self.root.unbind(sequence)
            except tk.TclError:
                pass

    def logout(self) -> None:
        if messagebox.askyesno("Выход", "Выйти из аккаунта?", parent=self.root):
            self.shutdown()
            self.on_logout()

    # ---------- тема и строка состояния ----------
    def apply_theme(self) -> None:
        p = self.palette = DARK if self.dark else LIGHT
        s = self.style
        self.root.configure(bg=p["bg"])
        s.configure(".", background=p["bg"], foreground=p["fg"], fieldbackground=p["panel"])
        s.configure("TFrame", background=p["bg"])
        s.configure("TLabel", background=p["bg"], foreground=p["fg"])
        s.configure("Status.TLabel", background=p["bar"], foreground=p["fg"],
                    padding=4, font=("Arial", 10))
        s.configure("TNotebook", background=p["bg"])
        s.configure("TNotebook.Tab", font=("Arial", 11, "bold"), padding=[15, 5],
                    background=p["bar"], foreground=p["fg"])
        s.map("TNotebook.Tab", background=[("selected", p["accent"])],
              foreground=[("selected", "white")])
        s.configure("Treeview", font=("Arial", 10), rowheight=28, background=p["panel"],
                    fieldbackground=p["panel"], foreground=p["fg"])
        s.map("Treeview", background=[("selected", p["accent"])],
              foreground=[("selected", "white")])
        s.configure("Treeview.Heading", font=("Arial", 11, "bold"),
                    background=p["bar"], foreground=p["fg"])
        s.configure("TEntry", fieldbackground=p["panel"], foreground=p["fg"])
        s.configure("TCombobox", fieldbackground=p["panel"], foreground=p["fg"])
        s.configure("TButton", padding=6)
        s.configure("Accent.TButton", background=p["accent"], foreground="white",
                    font=("Arial", 11, "bold"))
        s.map("Accent.TButton", background=[("active", p["accent_dark"])])

    def toggle_theme(self, _event=None) -> None:
        self.dark = not self.dark
        self.apply_theme()
        for key in self._rows:
            self._render(key)
        self.update_status("🌙 Тёмная тема" if self.dark else "☀️ Светлая тема")

    def _build_status_bar(self) -> None:
        self.status = ttk.Label(self.root, text=READY_TEXT, style="Status.TLabel", anchor=tk.W)
        self.status.pack(side=tk.BOTTOM, fill=tk.X)

    def update_status(self, message: str, error: bool = False) -> None:
        self.status.config(text=message,
                           foreground=self.palette["error"] if error else self.palette["fg"])
        if self._status_job is not None:
            self.root.after_cancel(self._status_job)
        self._status_job = self.root.after(
            4000, lambda: self.status.config(text=READY_TEXT, foreground=self.palette["fg"]))

    # ---------- фоновые задачи ----------
    def run_async(self, work, on_done=None, on_error=None) -> None:
        """Выполнить work() в потоке; on_done/on_error вызываются уже в потоке интерфейса."""
        self._pending += 1
        self.progress.start(10)

        def target():
            try:
                self._queue.put((on_done, work(), None))
            except Exception as exc:  # noqa: BLE001 - показываем любую ошибку пользователю
                self._queue.put((on_error, None, exc))

        threading.Thread(target=target, daemon=True).start()

    def _poll(self) -> None:
        try:
            while True:
                callback, result, exc = self._queue.get_nowait()
                self._pending = max(0, self._pending - 1)
                if self._pending == 0:
                    self.progress.stop()
                if exc is not None:
                    if callback:
                        callback(exc)
                    else:
                        self.update_status(f"❌ {exc}", error=True)
                elif callback:
                    callback(result)
        except queue.Empty:
            pass
        self._poll_job = self.root.after(self.POLL_MS, self._poll)

    def _fail(self, exc: Exception) -> None:
        self.update_status(f"❌ {exc}", error=True)

    # ---------- меню и горячие клавиши ----------
    def _build_menu(self) -> None:
        is_admin = self.user.role == ROLE_ADMIN
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        data_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="📊 Данные", menu=data_menu)
        for index, spec in enumerate(self.specs):
            data_menu.add_command(label=spec.title,
                                  command=lambda i=index: self.notebook.select(i))
        if is_admin:
            data_menu.add_separator()
            data_menu.add_command(label="➕ Добавить клиента", command=self.add_client_window)
            data_menu.add_command(label="📷 Добавить фотосессию", command=self.add_session_window)
        if self.user.role == ROLE_CLIENT:
            data_menu.add_separator()
            data_menu.add_command(label="✏️ Написать отзыв", command=self.write_review_window)

        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="🛠️ Инструменты", menu=tools_menu)
        if is_admin:
            tools_menu.add_command(label="📊 Графики (Ctrl+G)", command=self.show_charts)
        tools_menu.add_command(label="📎 Экспорт в Excel (Ctrl+E)", command=self.export_current_table)
        tools_menu.add_command(label="🔄 Обновить (F5)", command=self.load_current)
        tools_menu.add_command(label="🎨 Сменить тему (Ctrl+T)", command=self.toggle_theme)

        report_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="📈 Отчёты", menu=report_menu)
        if is_admin:
            report_menu.add_command(label="💰 Выручка и услуги", command=self.show_charts)
            report_menu.add_command(label="🏆 Топ фотографов", command=self.show_top_photographers)
        elif self.user.role == ROLE_CLIENT:
            report_menu.add_command(label="💸 Мои расходы", command=self.show_my_expenses)
        elif self.user.role == ROLE_PHOTOGRAPHER:
            report_menu.add_command(label="💵 Мои доходы", command=self.show_my_income)

        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="❓ Справка", menu=help_menu)
        help_menu.add_command(label="ℹ️ О программе", command=self.show_about)
        help_menu.add_command(label="🚪 Выйти", command=self.logout)

    def _bind_shortcuts(self) -> None:
        self.root.bind("<Control-t>", self.toggle_theme)
        self.root.bind("<Control-e>", self.export_current_table)
        self.root.bind("<Control-g>", self.show_charts)
        self.root.bind("<Control-f>", self.focus_search)
        self.root.bind("<F5>", lambda _e: self.load_current())

    def focus_search(self, _event=None) -> None:
        spec = self.current_spec()
        if spec:
            self.search_entries[spec.key].focus_set()

    # ---------- вкладки и таблицы ----------
    def _build_tabs(self) -> None:
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 0))
        wide = {"Отзыв", "Описание", "Адрес"}

        for spec in self.specs:
            frame = ttk.Frame(self.notebook)
            self.notebook.add(frame, text=spec.title)

            top = ttk.Frame(frame)
            top.pack(fill=tk.X, padx=6, pady=6)
            ttk.Label(top, text="🔍 Поиск:").pack(side=tk.LEFT)
            var = tk.StringVar()
            var.trace_add("write", lambda *_a, k=spec.key: self._render(k))
            entry = ttk.Entry(top, textvariable=var, width=32)
            entry.pack(side=tk.LEFT, padx=6)
            self.search_vars[spec.key] = var
            self.search_entries[spec.key] = entry
            if spec.key == "my_reviews":
                ttk.Button(top, text="✏️ Написать отзыв", style="Accent.TButton",
                           command=self.write_review_window).pack(side=tk.RIGHT)

            body = ttk.Frame(frame)
            body.pack(fill=tk.BOTH, expand=True)
            columns = [f"c{i}" for i in range(len(spec.headers))]
            tree = ttk.Treeview(body, show="headings", columns=columns)
            for i, header in enumerate(spec.headers):
                tree.heading(f"c{i}", text=header,
                             command=lambda k=spec.key, c=i: self.sort_by(k, c))
                width = 60 if i == 0 else (300 if header in wide else 140)
                tree.column(f"c{i}", width=width, anchor=tk.CENTER, stretch=True)
            vsb = ttk.Scrollbar(body, orient=tk.VERTICAL, command=tree.yview)
            hsb = ttk.Scrollbar(body, orient=tk.HORIZONTAL, command=tree.xview)
            tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
            tree.grid(row=0, column=0, sticky="nsew")
            vsb.grid(row=0, column=1, sticky="ns")
            hsb.grid(row=1, column=0, sticky="ew")
            body.rowconfigure(0, weight=1)
            body.columnconfigure(0, weight=1)

            tree.bind("<Double-1>", lambda _e, k=spec.key: self.edit_record(k))
            tree.bind("<Delete>", lambda _e: self.delete_selected())
            self.trees[spec.key] = tree
            self._rows[spec.key] = []

        self.notebook.bind("<<NotebookTabChanged>>", lambda _e: self.load_current())

    def current_spec(self) -> Optional[TableSpec]:
        if self.notebook is None:
            return None
        return self.specs[self.notebook.index(self.notebook.select())]

    def _params_for(self, spec: TableSpec):
        return (getattr(self.user, spec.param),) if spec.param else None

    def load_current(self) -> None:
        spec = self.current_spec()
        if spec:
            self.load(spec.key)

    def load(self, key: str) -> None:
        if key in self._loading:
            return
        spec = self.specs_by_key[key]
        self._loading.add(key)
        params = self._params_for(spec)

        def done(rows):
            self._loading.discard(key)
            self._rows[key] = [tuple(r) for r in rows]
            self._render(key)
            self.update_status(f"✅ {spec.title}: записей — {len(rows)}")

        def failed(exc):
            self._loading.discard(key)
            self._fail(exc)

        self.run_async(lambda: db.fetch_all(spec.query, params), done, failed)

    def _render(self, key: str) -> None:
        tree = self.trees[key]
        p = self.palette
        indexed = list(enumerate(self._rows[key]))

        state = self._sort.get(key)
        if state:
            col, reverse = state
            try:
                indexed.sort(key=lambda it: (it[1][col] is None, it[1][col]), reverse=reverse)
            except TypeError:
                indexed.sort(key=lambda it: fmt(it[1][col]), reverse=reverse)

        needle = self.search_vars[key].get().strip().lower()
        tree.delete(*tree.get_children())
        tree.tag_configure("even", background=p["row_even"], foreground=p["fg"])
        tree.tag_configure("odd", background=p["row_odd"], foreground=p["fg"])
        shown = 0
        for index, row in indexed:
            cells = [fmt(v) for v in row]
            if needle and not any(needle in c.lower() for c in cells):
                continue
            tree.insert("", tk.END, iid=str(index), values=cells,
                        tags=("even" if shown % 2 == 0 else "odd",))
            shown += 1

    def sort_by(self, key: str, column: int) -> None:
        current = self._sort.get(key)
        reverse = bool(current and current[0] == column and not current[1])
        self._sort[key] = (column, reverse)
        self._render(key)

    def selected_row(self, key: str):
        selection = self.trees[key].selection()
        return self._rows[key][int(selection[0])] if selection else None

    # ---------- универсальная форма ----------
    def open_form(self, title: str, fields: Sequence[Field], on_submit) -> None:
        """Диалог ввода. on_submit(values) может бросить db.DatabaseError или ValueError:
        текст ошибки покажется в окне, введённые данные не потеряются."""
        p = self.palette
        win = tk.Toplevel(self.root)
        win.title(title)
        win.configure(bg=p["bg"])
        win.transient(self.root)
        win.resizable(False, False)

        frame = ttk.Frame(win, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)
        widgets = {}
        for f in fields:
            ttk.Label(frame, text=f.label + (" *" if f.required else "")).pack(anchor=tk.W, pady=(8, 2))
            if f.kind == "combo":
                widget = ttk.Combobox(frame, values=list(f.choices), state="readonly", width=54)
                widget.set(f.initial)
            elif f.kind == "text":
                widget = tk.Text(frame, width=56, height=6, font=("Arial", 11),
                                 bg=p["panel"], fg=p["fg"], insertbackground=p["fg"],
                                 relief=tk.GROOVE, bd=2)
                widget.insert("1.0", f.initial)
            else:
                widget = ttk.Entry(frame, width=56)
                widget.insert(0, f.initial)
            widget.pack(fill=tk.X)
            widgets[f.name] = widget

        error = ttk.Label(frame, foreground=p["error"], wraplength=420)
        error.pack(anchor=tk.W, pady=(10, 0))

        def read(f: Field) -> str:
            w = widgets[f.name]
            return (w.get("1.0", tk.END) if f.kind == "text" else w.get()).strip()

        def submit() -> None:
            values = {}
            for f in fields:
                value = read(f)
                if not value:
                    if f.required:
                        error.config(text=f"Заполните поле «{f.label}»")
                        return
                    values[f.name] = None
                    continue
                if f.validator:
                    message = f.validator(value)
                    if message:
                        error.config(text=message)
                        return
                values[f.name] = value
            try:
                on_submit(values)
            except (db.DatabaseError, ValueError) as exc:
                error.config(text=str(exc))
                return
            win.destroy()

        buttons = ttk.Frame(frame)
        buttons.pack(fill=tk.X, pady=(15, 0))
        ttk.Button(buttons, text="Сохранить", style="Accent.TButton",
                   command=submit).pack(side=tk.RIGHT)
        ttk.Button(buttons, text="Отмена", command=win.destroy).pack(side=tk.RIGHT, padx=8)

        win.wait_visibility()
        win.grab_set()

    # ---------- правка и удаление (только администратор) ----------
    def edit_record(self, key: str) -> None:
        spec = self.specs_by_key[key]
        if self.user.role != ROLE_ADMIN or not spec.table:
            return
        row = self.selected_row(key)
        if row is None:
            return
        if not spec.editable:
            messagebox.showinfo(
                "Редактирование",
                "Для этой таблицы правка не предусмотрена.\n"
                "Запись можно удалить (клавиша Delete) и создать заново.",
                parent=self.root)
            return

        fields = [Field(c.column, c.label, "combo" if c.choices else "entry", c.choices,
                        fmt(row[c.idx]), c.required) for c in spec.editable]
        assignments = ", ".join(f"`{c.column}` = %s" for c in spec.editable)
        sql = f"UPDATE `{spec.table}` SET {assignments} WHERE `{spec.id_column}` = %s"

        def submit(values):
            params = [values[c.column] for c in spec.editable] + [row[0]]
            db.execute(sql, params)
            self.update_status(f"✅ Запись #{row[0]} обновлена")
            self.load(key)

        self.open_form(f"✏️ Запись #{row[0]}", fields, submit)

    def delete_selected(self) -> None:
        spec = self.current_spec()
        if self.user.role != ROLE_ADMIN or not spec or not spec.table:
            return
        row = self.selected_row(spec.key)
        if row is None:
            self.update_status("Выберите запись для удаления", error=True)
            return
        if not messagebox.askyesno(
                "Удаление", f"Удалить запись #{row[0]} из раздела «{spec.title}»?\n"
                            "Это действие нельзя отменить.", parent=self.root):
            return
        sql = f"DELETE FROM `{spec.table}` WHERE `{spec.id_column}` = %s"

        def done(_):
            self.update_status(f"🗑️ Запись #{row[0]} удалена")
            self.load(spec.key)

        def failed(exc):
            messagebox.showerror(
                "Не удалось удалить",
                f"{exc}\n\nВозможно, на эту запись ссылаются другие таблицы.",
                parent=self.root)

        self.run_async(lambda: db.execute(sql, (row[0],)), done, failed)

    # ---------- добавление данных ----------
    def add_client_window(self) -> None:
        fields = [Field("fio", "ФИО"),
                  Field("phone", "Телефон", validator=check_phone),
                  Field("email", "Email", validator=check_email)]

        def submit(v):
            db.execute(
                "INSERT INTO клиент (ФИО, Телефон, email, дата_регистрации) "
                "VALUES (%s, %s, %s, CURDATE())", (v["fio"], v["phone"], v["email"]))
            self.update_status("✅ Клиент добавлен")
            if "clients" in self.specs_by_key:
                self.load("clients")

        self.open_form("➕ Новый клиент", fields, submit)

    def add_session_window(self) -> None:
        def work():
            return {
                "clients": db.fetch_all("SELECT id_клиента, ФИО FROM клиент ORDER BY ФИО"),
                "photographers": db.fetch_all("SELECT id_фотографа, ФИО FROM фотограф ORDER BY ФИО"),
                "services": db.fetch_all("SELECT id_услуги, название, стоимость FROM услуга ORDER BY название"),
                "locations": db.fetch_all("SELECT id_локации, название FROM локация ORDER BY название"),
            }

        self.run_async(work, self._open_session_form, self._fail)

    def _open_session_form(self, data) -> None:
        def label(r):
            return f"{r[0]} — {r[1]}"

        prices = {label(r): r[2] for r in data["services"]}
        fields = [
            Field("client", "Клиент", "combo", [label(r) for r in data["clients"]]),
            Field("photographer", "Фотограф", "combo", [label(r) for r in data["photographers"]]),
            Field("service", "Услуга", "combo", list(prices)),
            Field("location", "Локация", "combo", [label(r) for r in data["locations"]], required=False),
            Field("date", "Дата (ГГГГ-ММ-ДД)", initial=date.today().isoformat(), validator=check_date),
            Field("time", "Время (ЧЧ:ММ)", initial="12:00", validator=check_time),
            Field("duration", "Длительность, часов", initial="1", validator=check_positive),
            Field("amount", "Сумма, ₽ (пусто — цена услуги)", required=False, validator=check_positive),
        ]

        def entity_id(text):
            return int(text.split(" — ")[0])

        def submit(v):
            photographer_id = entity_id(v["photographer"])
            busy = db.fetch_one(
                "SELECT COUNT(*) FROM фотосессия WHERE id_фотографа = %s "
                "AND дата = %s AND время = %s AND статус <> %s",
                (photographer_id, v["date"], v["time"], STATUS_CANCELLED))
            if busy and busy[0]:
                raise ValueError("У этого фотографа уже есть съёмка на это время")
            amount = float(v["amount"].replace(",", ".")) if v["amount"] else prices[v["service"]]
            db.execute(
                "INSERT INTO фотосессия (id_клиента, id_фотографа, id_услуги, id_локации, "
                "дата, время, длительность, сумма, статус) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (entity_id(v["client"]), photographer_id, entity_id(v["service"]),
                 entity_id(v["location"]) if v["location"] else None,
                 v["date"], v["time"], float(v["duration"].replace(",", ".")),
                 amount, STATUS_PLANNED))
            self.update_status("✅ Фотосессия добавлена")
            if "sessions" in self.specs_by_key:
                self.load("sessions")

        self.open_form("📷 Новая фотосессия", fields, submit)

    def write_review_window(self) -> None:
        if self.user.role != ROLE_CLIENT:
            return
        sql = """SELECT с.id_сессии, у.название, ф.ФИО, с.дата
                 FROM фотосессия с
                 JOIN услуга у ON с.id_услуги = у.id_услуги
                 JOIN фотограф ф ON с.id_фотографа = ф.id_фотографа
                 WHERE с.id_клиента = %s AND с.статус = %s
                   AND с.id_сессии NOT IN (SELECT id_сессии FROM отзыв WHERE id_сессии IS NOT NULL)"""
        params = (self.user.client_id, STATUS_DONE)
        self.run_async(lambda: db.fetch_all(sql, params), self._open_review_form, self._fail)

    def _open_review_form(self, sessions) -> None:
        if not sessions:
            messagebox.showinfo("Отзыв", "У вас нет завершённых фотосессий без отзыва.",
                                parent=self.root)
            return
        options = {f"#{s[0]} — {s[1]} (фотограф: {s[2]}, {fmt(s[3])})": s[0] for s in sessions}
        fields = [Field("session", "Фотосессия", "combo", list(options)),
                  Field("rating", "Оценка", "combo", ["1", "2", "3", "4", "5"]),
                  Field("text", "Текст отзыва", "text")]

        def submit(v):
            db.execute(
                "INSERT INTO отзыв (id_сессии, оценка, текст_отзыва, дата_отзыва) "
                "VALUES (%s, %s, %s, NOW())",
                (options[v["session"]], int(v["rating"]), v["text"]))
            self.update_status("✅ Спасибо за отзыв!")
            self.load("my_reviews")

        self.open_form("✏️ Написать отзыв", fields, submit)

    # ---------- отчёты ----------
    def _table_window(self, title: str, headers: Sequence[str], rows) -> None:
        win = tk.Toplevel(self.root)
        win.title(title)
        win.geometry("640x420")
        win.configure(bg=self.palette["bg"])
        columns = [f"c{i}" for i in range(len(headers))]
        tree = ttk.Treeview(win, show="headings", columns=columns)
        for i, header in enumerate(headers):
            tree.heading(f"c{i}", text=header)
            tree.column(f"c{i}", anchor=tk.CENTER, width=180)
        tree.tag_configure("even", background=self.palette["row_even"])
        tree.tag_configure("odd", background=self.palette["row_odd"])
        for n, row in enumerate(rows):
            tree.insert("", tk.END, values=[fmt(v) for v in row],
                        tags=("even" if n % 2 == 0 else "odd",))
        tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        if not rows:
            self.update_status("Нет данных для отчёта")

    def _report(self, title, headers, query, params=None) -> None:
        self.run_async(lambda: db.fetch_all(query, params),
                       lambda rows: self._table_window(title, headers, rows), self._fail)

    def show_top_photographers(self) -> None:
        self._report(
            "🏆 Топ фотографов", ("Фотограф", "Проведено сессий", "Выручка, ₽"),
            """SELECT ф.ФИО, COUNT(с.id_сессии), COALESCE(SUM(с.сумма), 0)
               FROM фотограф ф
               LEFT JOIN фотосессия с ON с.id_фотографа = ф.id_фотографа AND с.статус = %s
               GROUP BY ф.id_фотографа, ф.ФИО ORDER BY 3 DESC LIMIT 10""",
            (STATUS_DONE,))

    def show_my_expenses(self) -> None:
        self._report("💸 Мои расходы", ("Месяц", "Сессий", "Потрачено, ₽"),
                     MONTHLY_SQL.format(column="id_клиента"), (self.user.client_id, STATUS_DONE))

    def show_my_income(self) -> None:
        self._report("💵 Мои доходы", ("Месяц", "Съёмок", "Заработано, ₽"),
                     MONTHLY_SQL.format(column="id_фотографа"),
                     (self.user.photographer_id, STATUS_DONE))

    def show_charts(self, _event=None) -> None:
        if self.user.role != ROLE_ADMIN:  # финансы студии видит только администратор
            return

        def work():
            revenue = db.fetch_all(
                "SELECT DATE_FORMAT(дата, '%%Y-%%m') AS месяц, SUM(сумма) FROM фотосессия "
                "WHERE статус = %s GROUP BY месяц ORDER BY месяц DESC LIMIT 12", (STATUS_DONE,))
            top = db.fetch_all(
                "SELECT у.название, COUNT(*) FROM фотосессия с "
                "JOIN услуга у ON с.id_услуги = у.id_услуги "
                "GROUP BY у.id_услуги, у.название ORDER BY 2 DESC LIMIT 5")
            return revenue, top

        self.run_async(work, self._open_charts, self._fail)

    def _open_charts(self, data) -> None:
        revenue, top = data
        p = self.palette
        win = tk.Toplevel(self.root)
        win.title("📊 Аналитика")
        win.geometry("900x640")
        win.configure(bg=p["bg"])
        notebook = ttk.Notebook(win)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        def embed(tab_title, rows, draw):
            frame = ttk.Frame(notebook)
            notebook.add(frame, text=tab_title)
            if not rows:
                ttk.Label(frame, text="Пока нет данных для графика").pack(expand=True)
                return
            fig = Figure(figsize=(9, 5), facecolor=p["bg"])
            ax = fig.add_subplot(111)
            ax.set_facecolor(p["panel"])
            draw(ax, rows)
            canvas = FigureCanvasTkAgg(fig, frame)
            canvas.draw()
            canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        def draw_revenue(ax, rows):
            rows = list(reversed(rows))
            ax.bar([r[0] for r in rows], [float(r[1]) for r in rows], color=p["accent"])
            ax.set_title("Выручка по месяцам", color=p["fg"])
            ax.set_ylabel("Выручка, ₽", color=p["fg"])
            ax.tick_params(axis="x", rotation=45, colors=p["fg"])
            ax.tick_params(axis="y", colors=p["fg"])

        def draw_services(ax, rows):
            ax.pie([r[1] for r in rows], labels=[r[0] for r in rows], autopct="%1.1f%%",
                   textprops={"color": p["fg"]})
            ax.set_title("Популярность услуг", color=p["fg"])

        embed("💰 Выручка", revenue, draw_revenue)
        embed("✨ Топ услуг", top, draw_services)

    # ---------- экспорт и справка ----------
    def export_current_table(self, _event=None) -> None:
        spec = self.current_spec()
        rows = self._rows.get(spec.key) if spec else None
        if not rows:
            self.update_status("Нет данных для экспорта", error=True)
            return
        path = filedialog.asksaveasfilename(
            parent=self.root, defaultextension=".xlsx", initialfile=f"{spec.key}.xlsx",
            filetypes=[("Excel", "*.xlsx")])
        if not path:
            return
        headers = list(spec.headers)
        data = [[fmt(v) for v in row] for row in rows]

        def work():
            pd.DataFrame(data, columns=headers).to_excel(path, index=False)
            return path

        self.run_async(work, lambda p: self.update_status(f"✅ Экспортировано: {p}"), self._fail)

    def show_about(self) -> None:
        messagebox.showinfo(
            "О программе",
            "📸 Информационная система «Фотостудия»\n\n"
            "Python · Tkinter · MySQL · matplotlib · pandas\n"
            f"Вы вошли как: {self.user.name} ({self.user.role})\n\n"
            "Горячие клавиши:\n"
            "Ctrl+F — поиск, F5 — обновить, Ctrl+E — экспорт,\n"
            "Ctrl+G — графики, Ctrl+T — тема, Delete — удалить запись",
            parent=self.root)
