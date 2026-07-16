from tkinter import ttk
from typing import TYPE_CHECKING

from core.gui.dialogs.dialog import Dialog
from core.gui.themes import PADY

if TYPE_CHECKING:
    from core.gui.app import Application


class DockerImageConflictDialog(Dialog):
    """Prompt for replacing or reusing CORE compatibility images."""

    def __init__(self, app: "Application", images: list[str]) -> None:
        super().__init__(app, "Compatibility Image Exists")
        self.images = images
        self.choice: str | None = None
        self.draw()

    def draw(self) -> None:
        self.top.columnconfigure(0, weight=1)
        image_list = "\n".join(self.images)
        message = (
            "The following CORE compatibility images already exist:\n\n"
            f"{image_list}\n\n"
            "Choose whether to rebuild them or use the existing images."
        )
        ttk.Label(self.top, text=message, justify="left").grid(sticky="w", pady=PADY)
        buttons = ttk.Frame(self.top)
        buttons.grid(sticky="ew")
        buttons.columnconfigure((0, 1, 2), weight=1)
        ttk.Button(
            buttons, text="Remove Existing", command=lambda: self.select("remove")
        ).grid(row=0, column=0, sticky="ew")
        ttk.Button(
            buttons, text="Use Existing", command=lambda: self.select("reuse")
        ).grid(row=0, column=1, padx=PADY, sticky="ew")
        ttk.Button(buttons, text="Cancel", command=self.destroy).grid(
            row=0, column=2, sticky="ew"
        )

    def select(self, choice: str) -> None:
        self.choice = choice
        self.destroy()
