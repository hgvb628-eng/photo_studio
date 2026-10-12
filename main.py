"""Точка входа: python main.py"""
import tkinter as tk

from app import PhotoStudioApp
from login import LoginWindow


def main() -> None:
    root = tk.Tk()
    current = {"view": None}

    def clear() -> None:
        view = current["view"]
        if view is not None and hasattr(view, "shutdown"):
            view.shutdown()
        for widget in root.winfo_children():
            widget.destroy()
        try:
            root.config(menu="")
        except tk.TclError:
            root.config(menu=tk.Menu(root))

    def show_login() -> None:
        clear()
        current["view"] = LoginWindow(root, on_success=show_app)

    def show_app(user) -> None:
        clear()
        current["view"] = PhotoStudioApp(root, user, on_logout=show_login)

    show_login()
    root.mainloop()


if __name__ == "__main__":
    main()
