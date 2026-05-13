"""
Service configuration dialog
"""
import logging
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, simpledialog, ttk
from typing import TYPE_CHECKING

import grpc

from core.api.grpc.wrappers import (
    ConfigOption,
    Node,
    ServiceData,
    ServiceValidationMode,
)
from core.gui.dialogs.dialog import Dialog
from core.gui.themes import FRAME_PAD, PADX, PADY
from core.gui.widgets import CodeText, ConfigFrame, ListboxScroll

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from core.gui.app import Application
    from core.gui.coreclient import CoreClient


class ServiceConfigDialog(Dialog):
    def __init__(
        self, master: tk.BaseWidget, app: "Application", service_name: str, node: Node
    ) -> None:
        title = f"{service_name} Service"
        super().__init__(app, title, master=master)
        self.core: "CoreClient" = app.core
        self.node: Node = node
        self.service_name: str = service_name
        self.radiovar: tk.IntVar = tk.IntVar(value=2)
        self.directories: list[str] = []
        self.templates: list[str] = []
        self.rendered: dict[str, str] = {}
        self.dependencies: list[str] = []
        self.executables: list[str] = []
        self.startup_commands: list[str] = []
        self.validation_commands: list[str] = []
        self.shutdown_commands: list[str] = []
        self.default_startup: list[str] = []
        self.default_validate: list[str] = []
        self.default_shutdown: list[str] = []
        self.validation_mode: ServiceValidationMode | None = None
        self.validation_time: int | None = None
        self.validation_period: tk.DoubleVar = tk.DoubleVar()
        self.modes: list[str] = []
        self.mode_configs: dict[str, dict[str, str]] = {}
        self.notebook: ttk.Notebook | None = None
        self.templates_combobox: ttk.Combobox | None = None
        self.modes_combobox: ttk.Combobox | None = None
        self.startup_commands_listbox: tk.Listbox | None = None
        self.shutdown_commands_listbox: tk.Listbox | None = None
        self.validate_commands_listbox: tk.Listbox | None = None
        self.validation_time_entry: ttk.Entry | None = None
        self.validation_mode_entry: ttk.Entry | None = None
        self.directories_listbox: tk.Listbox | None = None
        self.files_listbox: tk.Listbox | None = None
        self.default_directories: list[str] = []
        self.default_files: list[str] = []
        self.template_text: CodeText | None = None
        self.rendered_text: CodeText | None = None
        self.validation_period_entry: ttk.Entry | None = None
        self.original_service_files: dict[str, str] = {}
        self.temp_service_files: dict[str, str] = {}
        self.modified_files: set[str] = set()
        self.config_frame: ConfigFrame | None = None
        self.default_config: dict[str, str] = {}
        self.config: dict[str, ConfigOption] = {}
        self.has_error: bool = False
        self.load()
        if not self.has_error:
            self.draw()

    def load(self) -> None:
        try:
            self.core.start_session(definition=True)
            service = self.core.services[self.service_name]
            self.description = service.description
            self.dependencies = service.dependencies[:]
            self.executables = service.executables[:]
            self.directories = service.directories[:]
            self.templates = service.files[:]
            self.default_directories = service.directories[:]
            self.default_files = service.files[:]
            self.default_dependencies = service.dependencies[:]
            self.default_executables = service.executables[:]
            self.startup_commands = service.startup[:]
            self.validation_commands = service.validate[:]
            self.shutdown_commands = service.shutdown[:]
            self.default_startup = service.startup[:]
            self.default_validate = service.validate[:]
            self.default_shutdown = service.shutdown[:]
            self.validation_mode = service.validation_mode
            self.validation_time = service.validation_timer
            self.validation_period.set(service.validation_period)
            defaults = self.core.get_service_defaults(self.node.id, self.service_name)
            self.original_service_files = defaults.templates
            self.temp_service_files = dict(self.original_service_files)
            self.modes = sorted(defaults.modes)
            self.mode_configs = defaults.modes
            self.config = ConfigOption.from_dict(defaults.config)
            self.default_config = {x.name: x.value for x in self.config.values()}
            self.rendered = self.core.get_service_rendered(
                self.node.id, self.service_name
            )
            service_config = self.node.service_configs.get(self.service_name)
            if service_config:
                for key, value in service_config.config.items():
                    self.config[key].value = value
                logger.info("default config: %s", self.default_config)
                for file, data in service_config.templates.items():
                    self.modified_files.add(file)
                    self.temp_service_files[file] = data
                # Load custom commands from service config if available
                if service_config.startup:
                    self.startup_commands = list(service_config.startup)
                if service_config.shutdown:
                    self.shutdown_commands = list(service_config.shutdown)
                if service_config.validate:
                    self.validation_commands = list(service_config.validate)
                if service_config.directories:
                    self.directories = list(service_config.directories)
                if service_config.files:
                    self.templates = list(service_config.files)
        except grpc.RpcError as e:
            self.app.show_grpc_exception("Get Service Error", e)
            self.has_error = True

    def draw(self) -> None:
        self.top.columnconfigure(0, weight=1)
        self.top.rowconfigure(1, weight=1)

        if self.description:
            label = ttk.Label(self.top, text=self.description, font=("TkDefaultFont", 10, "italic"))
            label.grid(sticky=tk.W, padx=PADX, pady=PADY)

        # draw notebook
        self.notebook = ttk.Notebook(self.top)
        self.notebook.grid(sticky=tk.NSEW, pady=PADY)
        self.draw_tab_files()
        self.draw_tab_dirs()
        if self.config:
            self.draw_tab_config()
        self.draw_tab_startstop()
        self.draw_tab_validation()
        self.draw_buttons()

    def draw_tab_dirs(self) -> None:
        tab = ttk.Frame(self.notebook, padding=FRAME_PAD)
        tab.grid(sticky=tk.NSEW)
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)
        self.notebook.add(tab, text="Directories")

        label = ttk.Label(tab, text="Private directories that will be created on the node.")
        label.grid(pady=PADY)

        listbox_scroll = ListboxScroll(tab)
        listbox_scroll.listbox.config(height=10)
        listbox_scroll.grid(sticky=tk.NSEW)
        self.directories_listbox = listbox_scroll.listbox
        for directory in self.directories:
            self.directories_listbox.insert(tk.END, directory)

        button_frame = ttk.Frame(tab)
        button_frame.grid(pady=(5, 0))
        button = ttk.Button(button_frame, text="Add", command=self.click_add_directory)
        button.grid(row=0, column=0, padx=PADX)
        button = ttk.Button(
            button_frame, text="Browse", command=self.click_browse_directory
        )
        button.grid(row=0, column=1, padx=PADX)
        button = ttk.Button(
            button_frame, text="Remove", command=self.click_remove_directory
        )
        button.grid(row=0, column=2)

    def draw_tab_files(self) -> None:
        tab = ttk.Frame(self.notebook, padding=FRAME_PAD)
        tab.grid(sticky=tk.NSEW)
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(2, weight=1)
        self.notebook.add(tab, text="Files")

        label = ttk.Label(
            tab, text="Files and templates that will be used for this service."
        )
        label.grid(pady=PADY)

        frame = ttk.Frame(tab)
        frame.grid(sticky=tk.NSEW, pady=PADY)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        # files
        label_frame = ttk.LabelFrame(frame, text="Files", padding=FRAME_PAD)
        label_frame.grid(row=0, column=0, sticky=tk.NSEW)
        label_frame.columnconfigure(0, weight=1)
        label_frame.rowconfigure(0, weight=1)
        listbox_scroll = ListboxScroll(label_frame)
        listbox_scroll.listbox.config(height=4)
        listbox_scroll.grid(sticky=tk.NSEW)
        self.files_listbox = listbox_scroll.listbox
        self.files_listbox.bind("<<ListboxSelect>>", self.handle_template_changed)
        for template in self.templates:
            self.files_listbox.insert(tk.END, template)
        button_frame = ttk.Frame(label_frame)
        button_frame.grid(row=1, column=0, pady=(5, 0))
        button = ttk.Button(button_frame, text="Add", command=self.click_add_file)
        button.grid(row=0, column=0, padx=PADX)
        button = ttk.Button(button_frame, text="Import", command=self.click_import_file)
        button.grid(row=0, column=1, padx=PADX)
        button = ttk.Button(button_frame, text="Remove", command=self.click_remove_file)
        button.grid(row=0, column=2)
        # draw file template tab
        notebook = ttk.Notebook(tab)
        notebook.rowconfigure(0, weight=1)
        notebook.columnconfigure(0, weight=1)
        notebook.grid(sticky=tk.NSEW, pady=PADY)
        # draw rendered file tab
        rendered_tab = ttk.Frame(notebook, padding=FRAME_PAD)
        rendered_tab.grid(sticky=tk.NSEW)
        rendered_tab.rowconfigure(0, weight=1)
        rendered_tab.columnconfigure(0, weight=1)
        notebook.add(rendered_tab, text="Rendered")
        self.rendered_text = CodeText(rendered_tab)
        self.rendered_text.grid(sticky=tk.NSEW)
        self.rendered_text.text.bind("<FocusOut>", self.update_template_file_data)
        # draw template file tab
        template_tab = ttk.Frame(notebook, padding=FRAME_PAD)
        template_tab.grid(sticky=tk.NSEW)
        template_tab.rowconfigure(0, weight=1)
        template_tab.columnconfigure(0, weight=1)
        notebook.add(template_tab, text="Template")
        self.template_text = CodeText(template_tab)
        self.template_text.grid(sticky=tk.NSEW)
        self.template_text.text.bind("<FocusOut>", self.update_template_file_data)
        if self.templates:
            self.files_listbox.selection_set(0)
            template_name = self.templates[0]
            temp_data = self.temp_service_files.get(template_name, "")
            self.template_text.set_text(temp_data)
            self.template_text.text.configure(state=tk.DISABLED)
            self.rendered_text.set_text(temp_data)
        else:
            self.template_text.text.configure(state=tk.DISABLED)
            self.rendered_text.text.configure(state=tk.DISABLED)

    def draw_tab_config(self) -> None:
        tab = ttk.Frame(self.notebook, padding=FRAME_PAD)
        tab.grid(sticky=tk.NSEW)
        tab.columnconfigure(0, weight=1)
        self.notebook.add(tab, text="Configuration")

        if self.modes:
            frame = ttk.Frame(tab)
            frame.grid(sticky=tk.EW, pady=PADY)
            frame.columnconfigure(1, weight=1)
            label = ttk.Label(frame, text="Modes")
            label.grid(row=0, column=0, padx=PADX)
            self.modes_combobox = ttk.Combobox(
                frame, values=self.modes, state="readonly"
            )
            self.modes_combobox.bind("<<ComboboxSelected>>", self.handle_mode_changed)
            self.modes_combobox.grid(row=0, column=1, sticky=tk.EW, pady=PADY)

        logger.info("service config: %s", self.config)
        self.config_frame = ConfigFrame(tab, self.app, self.config)
        self.config_frame.draw_config()
        self.config_frame.grid(sticky=tk.NSEW, pady=PADY)
        tab.rowconfigure(self.config_frame.grid_info()["row"], weight=1)

    def draw_tab_startstop(self) -> None:
        tab = ttk.Frame(self.notebook, padding=FRAME_PAD)
        tab.grid(sticky=tk.NSEW)
        tab.columnconfigure(0, weight=1)
        for i in range(3):
            tab.rowconfigure(i, weight=1)
        self.notebook.add(tab, text="Startup/Shutdown")
        # tab 3
        for i in range(3):
            label_frame = None
            command_list = None
            listbox_attr = None
            if i == 0:
                label_frame = ttk.LabelFrame(
                    tab, text="Startup Commands", padding=FRAME_PAD
                )
                command_list = self.startup_commands
                listbox_attr = "startup_commands_listbox"
            elif i == 1:
                label_frame = ttk.LabelFrame(
                    tab, text="Shutdown Commands", padding=FRAME_PAD
                )
                command_list = self.shutdown_commands
                listbox_attr = "shutdown_commands_listbox"
            elif i == 2:
                label_frame = ttk.LabelFrame(
                    tab, text="Validation Commands", padding=FRAME_PAD
                )
                command_list = self.validation_commands
                listbox_attr = "validate_commands_listbox"
            label_frame.columnconfigure(0, weight=1)
            label_frame.rowconfigure(0, weight=1)
            label_frame.grid(row=i, column=0, sticky=tk.NSEW, pady=PADY)
            listbox_scroll = ListboxScroll(label_frame)
            listbox_scroll.listbox.config(height=4)
            listbox_scroll.grid(sticky=tk.NSEW, row=0, column=0, columnspan=2)
            for command in command_list:
                listbox_scroll.listbox.insert("end", command)
            setattr(self, listbox_attr, listbox_scroll.listbox)
            # Add buttons for add/remove
            button_frame = ttk.Frame(label_frame)
            button_frame.grid(row=1, column=0, columnspan=2, pady=(5, 0))
            button_frame.columnconfigure(0, weight=1)
            button_frame.columnconfigure(1, weight=1)
            add_button = ttk.Button(
                button_frame,
                text="Add",
                command=lambda attr=listbox_attr: self.click_add_command(attr),
            )
            add_button.grid(row=0, column=0, sticky=tk.EW, padx=PADX)
            remove_button = ttk.Button(
                button_frame,
                text="Remove",
                command=lambda attr=listbox_attr: self.click_remove_command(attr),
            )
            remove_button.grid(row=0, column=1, sticky=tk.EW, padx=PADX)
            up_button = ttk.Button(
                button_frame,
                text="Up",
                command=lambda attr=listbox_attr: self.click_move_command(attr, -1),
            )
            up_button.grid(row=0, column=2, sticky=tk.EW, padx=PADX)
            down_button = ttk.Button(
                button_frame,
                text="Down",
                command=lambda attr=listbox_attr: self.click_move_command(attr, 1),
            )
            down_button.grid(row=0, column=3, sticky=tk.EW)

    def draw_tab_validation(self) -> None:
        tab = ttk.Frame(self.notebook, padding=FRAME_PAD)
        tab.grid(sticky=tk.EW)
        tab.columnconfigure(0, weight=1)
        self.notebook.add(tab, text="Validation", sticky=tk.NSEW)

        frame = ttk.Frame(tab)
        frame.grid(sticky=tk.EW, pady=PADY)
        frame.columnconfigure(1, weight=1)

        label = ttk.Label(frame, text="Validation Time")
        label.grid(row=0, column=0, sticky=tk.W, padx=PADX)
        self.validation_time_entry = ttk.Entry(frame)
        self.validation_time_entry.insert("end", str(self.validation_time))
        self.validation_time_entry.config(state=tk.DISABLED)
        self.validation_time_entry.grid(row=0, column=1, sticky=tk.EW, pady=PADY)

        label = ttk.Label(frame, text="Validation Mode")
        label.grid(row=1, column=0, sticky=tk.W, padx=PADX)
        if self.validation_mode == ServiceValidationMode.BLOCKING:
            mode = "BLOCKING"
        elif self.validation_mode == ServiceValidationMode.NON_BLOCKING:
            mode = "NON_BLOCKING"
        else:
            mode = "TIMER"
        self.validation_mode_entry = ttk.Entry(
            frame, textvariable=tk.StringVar(value=mode)
        )
        self.validation_mode_entry.insert("end", mode)
        self.validation_mode_entry.config(state=tk.DISABLED)
        self.validation_mode_entry.grid(row=1, column=1, sticky=tk.EW, pady=PADY)

        label = ttk.Label(frame, text="Validation Period")
        label.grid(row=2, column=0, sticky=tk.W, padx=PADX)
        self.validation_period_entry = ttk.Entry(
            frame, state=tk.DISABLED, textvariable=self.validation_period
        )
        self.validation_period_entry.grid(row=2, column=1, sticky=tk.EW, pady=PADY)
        tab.rowconfigure(1, weight=1)
        tab.rowconfigure(2, weight=1)

        label_frame = ttk.LabelFrame(tab, text="Executables", padding=FRAME_PAD)
        label_frame.grid(row=1, column=0, sticky=tk.NSEW, pady=PADY)
        label_frame.columnconfigure(0, weight=1)
        label_frame.rowconfigure(0, weight=1)
        listbox_scroll = ListboxScroll(label_frame)
        listbox_scroll.listbox.config(height=6)
        listbox_scroll.grid(sticky=tk.NSEW)
        self.executables_listbox = listbox_scroll.listbox
        for executable in self.executables:
            self.executables_listbox.insert("end", executable)
        button_frame = ttk.Frame(label_frame)
        button_frame.grid(row=1, column=0, pady=(5, 0))
        button = ttk.Button(button_frame, text="Add", command=self.click_add_executable)
        button.grid(row=0, column=0, padx=PADX)
        button = ttk.Button(button_frame, text="Remove", command=self.click_remove_executable)
        button.grid(row=0, column=1)

        label_frame = ttk.LabelFrame(tab, text="Dependencies", padding=FRAME_PAD)
        label_frame.grid(row=2, column=0, sticky=tk.NSEW, pady=PADY)
        label_frame.columnconfigure(0, weight=1)
        label_frame.rowconfigure(0, weight=1)
        listbox_scroll = ListboxScroll(label_frame)
        listbox_scroll.listbox.config(height=6)
        listbox_scroll.grid(sticky=tk.NSEW)
        self.dependencies_listbox = listbox_scroll.listbox
        for dependency in self.dependencies:
            self.dependencies_listbox.insert("end", dependency)
        button_frame = ttk.Frame(label_frame)
        button_frame.grid(row=1, column=0, pady=(5, 0))
        button = ttk.Button(button_frame, text="Add", command=self.click_add_dependency)
        button.grid(row=0, column=0, padx=PADX)
        button = ttk.Button(button_frame, text="Remove", command=self.click_remove_dependency)
        button.grid(row=0, column=1)

    def draw_buttons(self) -> None:
        frame = ttk.Frame(self.top)
        frame.grid(sticky=tk.EW)
        for i in range(4):
            frame.columnconfigure(i, weight=1)
        button = ttk.Button(frame, text="Apply", command=self.click_apply)
        button.grid(row=0, column=0, sticky=tk.EW, padx=PADX)
        button = ttk.Button(frame, text="Copy to...", command=self.click_copy_to)
        button.grid(row=0, column=1, sticky=tk.EW, padx=PADX)
        button = ttk.Button(frame, text="Defaults", command=self.click_defaults)
        button.grid(row=0, column=2, sticky=tk.EW, padx=PADX)
        button = ttk.Button(frame, text="Cancel", command=self.destroy)
        button.grid(row=0, column=3, sticky=tk.EW)

    def click_copy_to(self) -> None:
        self.update_template_file_data(None)
        service_config = ServiceData()
        if self.config_frame:
            self.config_frame.parse_config()
            service_config.config = {x.name: x.value for x in self.config.values()}
        for file in self.modified_files:
            service_config.templates[file] = self.temp_service_files[file]
        service_config.startup = list(self.startup_commands)
        service_config.shutdown = list(self.shutdown_commands)
        service_config.validate = list(self.validation_commands)
        service_config.directories = list(self.directories)
        service_config.files = list(self.templates)
        service_config.dependencies = list(self.dependencies)
        service_config.executables = list(self.executables)
        service_config.description = self.description or ""

        dialog = CopyToDialog(self.top, self.app, self.service_name, service_config, self.node)
        dialog.show()

    def click_apply(self) -> None:
        if self.startup_commands_listbox is not None:
            self.startup_commands = list(self.startup_commands_listbox.get(0, tk.END))
            self.shutdown_commands = list(self.shutdown_commands_listbox.get(0, tk.END))
            self.validation_commands = list(self.validate_commands_listbox.get(0, tk.END))
        if self.directories_listbox is not None:
            self.directories = list(self.directories_listbox.get(0, tk.END))
            self.templates = list(self.files_listbox.get(0, tk.END))
        if self.dependencies_listbox is not None:
            self.dependencies = list(self.dependencies_listbox.get(0, tk.END))
        if self.executables_listbox is not None:
            self.executables = list(self.executables_listbox.get(0, tk.END))
        self.update_template_file_data(None)
        current_listbox = self.master.current.listbox
        if not self.is_custom():
            self.node.service_configs.pop(self.service_name, None)
            current_listbox.itemconfig(current_listbox.curselection()[0], bg="")
        else:
            service_config = self.node.service_configs.setdefault(
                self.service_name, ServiceData()
            )
            if self.config_frame:
                self.config_frame.parse_config()
                service_config.config = {x.name: x.value for x in self.config.values()}
            for file in self.modified_files:
                service_config.templates[file] = self.temp_service_files[file]
            # Save custom commands and file/directory lists
            service_config.startup = list(self.startup_commands)
            service_config.shutdown = list(self.shutdown_commands)
            service_config.validate = list(self.validation_commands)
            service_config.directories = list(self.directories)
            service_config.files = list(self.templates)
            service_config.dependencies = list(self.dependencies)
            service_config.executables = list(self.executables)
            service_config.description = self.description or ""
            all_current = current_listbox.get(0, tk.END)
            current_listbox.itemconfig(all_current.index(self.service_name), bg="green")
        self.destroy()

    def click_add_command(self, listbox_attr: str) -> None:
        listbox = getattr(self, listbox_attr)
        # Create a simple entry dialog for adding a command
        dialog = tk.Toplevel(self.top)
        dialog.title("Add Command")
        dialog.transient(self.top)
        dialog.grab_set()

        main_frame = ttk.Frame(dialog)
        main_frame.pack(fill=tk.BOTH, expand=True)

        frame = ttk.Frame(main_frame)
        frame.pack(padx=20, pady=20)

        label = ttk.Label(frame, text="Command:")
        label.grid(row=0, column=0, sticky=tk.W, pady=5)
        entry = ttk.Entry(frame, width=50)
        entry.grid(row=0, column=1, sticky=tk.EW, pady=5)

        def add_command():
            cmd = entry.get().strip()
            if cmd:
                listbox.insert(tk.END, cmd)
                dialog.destroy()

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=1, column=0, columnspan=2, pady=10)
        add_btn = ttk.Button(btn_frame, text="Add", command=add_command)
        add_btn.pack(side=tk.LEFT, padx=5)
        cancel_btn = ttk.Button(btn_frame, text="Cancel", command=dialog.destroy)
        cancel_btn.pack(side=tk.LEFT, padx=5)

        # Focus entry and bind Enter key
        entry.focus_set()
        dialog.bind("<Return>", lambda e: add_command())

        # Wait for dialog to close
        self.top.wait_window(dialog)

    def click_remove_command(self, listbox_attr: str) -> None:
        listbox = getattr(self, listbox_attr)
        selection = listbox.curselection()
        if selection:
            listbox.delete(selection[0])

    def click_move_command(self, listbox_attr: str, direction: int) -> None:
        listbox = getattr(self, listbox_attr)
        selection = listbox.curselection()
        if not selection:
            return
        index = selection[0]
        new_index = index + direction
        if 0 <= new_index < listbox.size():
            cmd = listbox.get(index)
            listbox.delete(index)
            listbox.insert(new_index, cmd)
            listbox.selection_set(new_index)
            # sync internal list
            if listbox_attr == "startup_commands_listbox":
                self.startup_commands = list(listbox.get(0, tk.END))
            elif listbox_attr == "shutdown_commands_listbox":
                self.shutdown_commands = list(listbox.get(0, tk.END))
            elif listbox_attr == "validate_commands_listbox":
                self.validation_commands = list(listbox.get(0, tk.END))

    def handle_template_changed(self, event: tk.Event) -> None:
        selection = self.files_listbox.curselection()
        if not selection:
            return
        index = selection[0]
        template_name = self.files_listbox.get(index)
        temp_data = self.temp_service_files.get(template_name, "")
        original_data = self.original_service_files.get(template_name)
        self.template_text.text.configure(state=tk.NORMAL)
        if temp_data == original_data:
            self.template_text.set_text(temp_data)
        else:
            self.template_text.set_text("Rendered Modified")
        self.template_text.text.configure(state=tk.DISABLED)
        self.rendered_text.set_text(temp_data)

    def update_template_file_data(self, _event: tk.Event) -> None:
        selection = self.files_listbox.curselection()
        if not selection:
            return
        index = selection[0]
        template_name = self.files_listbox.get(index)
        template_data = self.rendered_text.get_text().strip()
        self.temp_service_files[template_name] = template_data
        original_data = self.original_service_files.get(template_name)
        if template_data != original_data:
            self.modified_files.add(template_name)
            self.template_text.text.configure(state=tk.NORMAL)
            self.template_text.set_text("Rendered Modified")
            self.template_text.text.configure(state=tk.DISABLED)
        else:
            self.modified_files.discard(template_name)
            self.template_text.text.configure(state=tk.NORMAL)
            self.template_text.set_text(template_data)
            self.template_text.text.configure(state=tk.DISABLED)

    def click_add_directory(self) -> None:
        name = simpledialog.askstring("Add Directory", "Enter directory path:")
        if name:
            if name in self.directories_listbox.get(0, tk.END):
                return
            self.directories_listbox.insert(tk.END, name)

    def click_browse_directory(self) -> None:
        path = filedialog.askdirectory(title="Select Private Directory")
        if path:
            if path in self.directories_listbox.get(0, tk.END):
                return
            self.directories_listbox.insert(tk.END, path)

    def click_remove_directory(self) -> None:
        selection = self.directories_listbox.curselection()
        if selection:
            index = selection[0]
            self.directories_listbox.delete(index)

    def click_add_dependency(self) -> None:
        name = simpledialog.askstring("Add Dependency", "Service name:")
        if name:
            if name in self.dependencies_listbox.get(0, tk.END):
                return
            self.dependencies_listbox.insert(tk.END, name)

    def click_remove_dependency(self) -> None:
        selection = self.dependencies_listbox.curselection()
        if selection:
            index = selection[0]
            self.dependencies_listbox.delete(index)

    def click_add_executable(self) -> None:
        name = simpledialog.askstring("Add Executable", "Executable name:")
        if name:
            if name in self.executables_listbox.get(0, tk.END):
                return
            self.executables_listbox.insert(tk.END, name)

    def click_remove_executable(self) -> None:
        selection = self.executables_listbox.curselection()
        if selection:
            index = selection[0]
            self.executables_listbox.delete(index)

    def click_add_file(self) -> None:
        name = simpledialog.askstring("Add File", "Enter file name:")
        if name:
            if name in self.files_listbox.get(0, tk.END):
                return
            self.files_listbox.insert(tk.END, name)
            self.temp_service_files[name] = ""
            self.files_listbox.selection_clear(0, tk.END)
            self.files_listbox.selection_set(tk.END)
            self.handle_template_changed(None)
            self.template_text.text.configure(state=tk.NORMAL)
            self.rendered_text.text.configure(state=tk.NORMAL)

    def click_import_file(self) -> None:
        path = filedialog.askopenfilename(title="Open File")
        if path:
            path = Path(path)
            name = path.name
            if name in self.files_listbox.get(0, tk.END):
                return
            try:
                data = path.read_text()
                self.files_listbox.insert(tk.END, name)
                self.temp_service_files[name] = data
                self.files_listbox.selection_clear(0, tk.END)
                self.files_listbox.selection_set(tk.END)
                self.handle_template_changed(None)
                self.template_text.text.configure(state=tk.NORMAL)
                self.rendered_text.text.configure(state=tk.NORMAL)
            except Exception as e:
                logger.error("error reading file: %s", e)
                self.app.show_error("Import Error", f"Error reading file: {e}")

    def click_remove_file(self) -> None:
        selection = self.files_listbox.curselection()
        if selection:
            index = selection[0]
            name = self.files_listbox.get(index)
            self.files_listbox.delete(index)
            if name in self.temp_service_files:
                del self.temp_service_files[name]
            self.modified_files.discard(name)
            if self.files_listbox.size() == 0:
                self.template_text.set_text("")
                self.rendered_text.set_text("")
                self.template_text.text.configure(state=tk.DISABLED)
                self.rendered_text.text.configure(state=tk.DISABLED)

    def handle_mode_changed(self, event: tk.Event) -> None:
        mode = self.modes_combobox.get()
        config = self.mode_configs[mode]
        logger.info("mode config: %s", config)
        self.config_frame.set_values(config)

    def is_custom(self) -> bool:
        has_custom_templates = len(self.modified_files) > 0
        has_custom_config = False
        if self.config_frame:
            current = self.config_frame.parse_config()
            has_custom_config = self.default_config != current
        has_custom_commands = (
            self.startup_commands != self.default_startup
            or self.shutdown_commands != self.default_shutdown
            or self.validation_commands != self.default_validate
        )
        has_custom_files = self.templates != self.default_files
        has_custom_directories = self.directories != self.default_directories
        has_custom_dependencies = self.dependencies != self.default_dependencies
        has_custom_executables = self.executables != self.default_executables
        return (
            has_custom_templates
            or has_custom_config
            or has_custom_commands
            or has_custom_files
            or has_custom_directories
            or has_custom_dependencies
            or has_custom_executables
        )

    def click_defaults(self) -> None:
        # reset data to defaults
        self.modified_files.clear()
        self.node.service_configs.pop(self.service_name, None)
        self.temp_service_files = dict(self.original_service_files)
        self.startup_commands = self.default_startup[:]
        self.shutdown_commands = self.default_shutdown[:]
        self.validation_commands = self.default_validate[:]
        self.directories = self.default_directories[:]
        self.templates = self.default_files[:]
        self.dependencies = self.default_dependencies[:]
        self.executables = self.default_executables[:]

        # update UI widgets
        if self.startup_commands_listbox:
            self.startup_commands_listbox.delete(0, tk.END)
            for cmd in self.startup_commands:
                self.startup_commands_listbox.insert(tk.END, cmd)
        if self.shutdown_commands_listbox:
            self.shutdown_commands_listbox.delete(0, tk.END)
            for cmd in self.shutdown_commands:
                self.shutdown_commands_listbox.insert(tk.END, cmd)
        if self.validate_commands_listbox:
            self.validate_commands_listbox.delete(0, tk.END)
            for cmd in self.validation_commands:
                self.validate_commands_listbox.insert(tk.END, cmd)
        if self.directories_listbox:
            self.directories_listbox.delete(0, tk.END)
            for directory in self.directories:
                self.directories_listbox.insert(tk.END, directory)
        if self.files_listbox:
            self.files_listbox.delete(0, tk.END)
            for file in self.templates:
                self.files_listbox.insert(tk.END, file)
            if self.templates:
                self.files_listbox.selection_set(0)
                self.handle_template_changed(None)
        if self.dependencies_listbox:
            self.dependencies_listbox.delete(0, tk.END)
            for dependency in self.dependencies:
                self.dependencies_listbox.insert(tk.END, dependency)
        if self.executables_listbox:
            self.executables_listbox.delete(0, tk.END)
            for executable in self.executables:
                self.executables_listbox.insert(tk.END, executable)

        if self.config_frame:
            logger.info("resetting defaults: %s", self.default_config)
            self.config_frame.set_values(self.default_config)

        # reset session definition and retrieve default rendered templates
        self.core.start_session(definition=True)
        self.rendered = self.core.get_service_rendered(self.node.id, self.service_name)
        logger.info("cleared service config: %s", self.node.service_configs)

    def append_commands(
        self, commands: list[str], listbox: tk.Listbox, to_add: list[str]
    ) -> None:
        for cmd in to_add:
            commands.append(cmd)
            listbox.insert(tk.END, cmd)


class CopyToDialog(Dialog):
    def __init__(
        self, master: tk.BaseWidget, app: "Application", service_name: str, service_config: ServiceData, source_node: Node
    ) -> None:
        self.service_name = service_name
        self.service_config = service_config
        self.source_node = source_node
        self.nodes_listbox = None
        super().__init__(app, f"Copy {service_name} to...", master=master)

    def draw(self) -> None:
        self.top.columnconfigure(0, weight=1)
        self.top.rowconfigure(1, weight=1)

        label = ttk.Label(self.top, text=f"Select nodes to copy '{self.service_name}' configuration to:")
        label.grid(sticky=tk.W, padx=PADX, pady=PADY)

        listbox_scroll = ListboxScroll(self.top)
        listbox_scroll.grid(sticky=tk.NSEW, pady=PADY)
        self.nodes_listbox = listbox_scroll.listbox
        self.nodes_listbox.config(selectmode=tk.MULTIPLE)

        # populate nodes
        session = self.app.core.get_session(self.app.core.session_id)
        for node_id in sorted(session.nodes):
            node = session.nodes[node_id]
            if node.id == self.source_node.id:
                continue
            # only show nodes that have this service enabled?
            # actually, 8.2.0 allowed copying to any node, but maybe filter by type?
            self.nodes_listbox.insert(tk.END, f"{node.id}: {node.name} ({node.type.name})")

        button_frame = ttk.Frame(self.top)
        button_frame.grid(sticky=tk.EW, pady=PADY)
        button_frame.columnconfigure(0, weight=1)
        button_frame.columnconfigure(1, weight=1)
        button_frame.columnconfigure(2, weight=1)

        button = ttk.Button(button_frame, text="All", command=self.click_all)
        button.grid(row=0, column=0, padx=PADX)
        button = ttk.Button(button_frame, text="Same Type", command=self.click_same_type)
        button.grid(row=0, column=1, padx=PADX)
        button = ttk.Button(button_frame, text="None", command=self.click_none)
        button.grid(row=0, column=2)

        draw_buttons_frame = ttk.Frame(self.top)
        draw_buttons_frame.grid(sticky=tk.EW)
        draw_buttons_frame.columnconfigure(0, weight=1)
        draw_buttons_frame.columnconfigure(1, weight=1)

        button = ttk.Button(draw_buttons_frame, text="Copy", command=self.click_copy)
        button.grid(row=0, column=0, padx=PADX, sticky=tk.EW)
        button = ttk.Button(draw_buttons_frame, text="Cancel", command=self.destroy)
        button.grid(row=0, column=1, sticky=tk.EW)

    def click_all(self) -> None:
        self.nodes_listbox.selection_set(0, tk.END)

    def click_same_type(self) -> None:
        self.click_none()
        session = self.app.core.get_session(self.app.core.session_id)
        for i, node_id in enumerate(sorted(session.nodes)):
            node = session.nodes[node_id]
            if node.id == self.source_node.id:
                continue
            if node.type == self.source_node.type:
                # adjust for the fact that we skipped source_node in the insert?
                # actually, we should find the correct index in the listbox
                # let's rebuild the index mapping
                pass
        
        # easier way: iterate listbox items
        for i in range(self.nodes_listbox.size()):
            item = self.nodes_listbox.get(i)
            node_id = int(item.split(":")[0])
            node = session.nodes[node_id]
            if node.type == self.source_node.type:
                self.nodes_listbox.selection_set(i)

    def click_none(self) -> None:
        self.nodes_listbox.selection_clear(0, tk.END)

    def click_copy(self) -> None:
        selection = self.nodes_listbox.curselection()
        if not selection:
            self.app.show_error("Copy Error", "No nodes selected.")
            return

        session = self.app.core.get_session(self.app.core.session_id)
        for index in selection:
            item = self.nodes_listbox.get(index)
            node_id = int(item.split(":")[0])
            node = session.nodes[node_id]
            # apply configuration
            node.service_configs[self.service_name] = self.service_config
            # ensure service is enabled on target node?
            if self.service_name not in node.services:
                node.services.append(self.service_name)
        
        self.app.show_info("Copy Success", f"Configuration copied to {len(selection)} nodes.")
        self.destroy()
