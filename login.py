"""Окно авторизации."""
import tkinter as tk
from tkinter import messagebox

import auth
import db


class LoginWindow:
    WIDTH, HEIGHT = 450, 380

    def __init__(self, root: tk.Tk, on_success):
        self.root = root
        self.on_success = on_success

        root.title("📸 Авторизация — Фотостудия")
        root.minsize(self.WIDTH, self.HEIGHT)
        root.geometry(self._centered_geometry())
        root.configure(bg="#2c3e50")

        header = tk.Frame(root, bg="#34495e", height=80)
        header.pack(fill=tk.X)
        tk.Label(header, text="📸 Фотостудия", font=("Arial", 20, "bold"),
                 bg="#34495e", fg="white").pack(pady=20)

        form = tk.Frame(root, bg="#2c3e50", padx=40, pady=30)
        form.pack(fill=tk.BOTH, expand=True)

        tk.Label(form, text="Логин:", font=("Arial", 12), bg="#2c3e50",
                 fg="white").pack(anchor=tk.W, pady=(10, 0))
        self.entry_login = tk.Entry(form, width=30, font=("Arial", 12),
                                    relief=tk.GROOVE, bd=2)
        self.entry_login.pack(fill=tk.X, pady=5)

        tk.Label(form, text="Пароль:", font=("Arial", 12), bg="#2c3e50",
                 fg="white").pack(anchor=tk.W, pady=(10, 0))
        self.entry_password = tk.Entry(form, width=30, font=("Arial", 12),
                                       show="*", relief=tk.GROOVE, bd=2)
        self.entry_password.pack(fill=tk.X, pady=5)

        self.button = tk.Button(form, text="🔓 Войти", command=self.login,
                                bg="#27ae60", fg="white", font=("Arial", 12, "bold"),
                                padx=20, pady=5, relief=tk.RAISED, bd=2, cursor="hand2")
        self.button.pack(pady=25)

        for entry in (self.entry_login, self.entry_password):
            entry.bind("<Return>", lambda _event: self.login())
        self.entry_login.focus_set()

    def _centered_geometry(self) -> str:
        x = (self.root.winfo_screenwidth() - self.WIDTH) // 2
        y = (self.root.winfo_screenheight() - self.HEIGHT) // 2
        return f"{self.WIDTH}x{self.HEIGHT}+{x}+{y}"

    def login(self) -> None:
        login = self.entry_login.get().strip()
        password = self.entry_password.get()

        if not login or not password:
            messagebox.showerror("Ошибка", "Введите логин и пароль", parent=self.root)
            return

        self.button.config(state=tk.DISABLED)
        self.root.config(cursor="watch")
        self.root.update_idletasks()
        try:
            user = auth.authenticate(login, password)
        except db.DatabaseError as exc:
            messagebox.showerror("Ошибка", str(exc), parent=self.root)
            return
        finally:
            self.root.config(cursor="")
            if self.button.winfo_exists():
                self.button.config(state=tk.NORMAL)

        if user is None:
            messagebox.showerror("Ошибка", "Неверный логин или пароль", parent=self.root)
            self.entry_password.delete(0, tk.END)
            return

        self.on_success(user)
