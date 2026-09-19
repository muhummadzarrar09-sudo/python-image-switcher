"""
Searchable Combobox with acceptance gate coloring - the core selector with search inside dropdown
"""
import customtkinter as ctk
from typing import List, Callable, Optional, Tuple
from src.converter.formats import ImageFormat, searchable_formats, FORMATS
from src.converter.validator import GateResult

class SearchableFormatDropdown(ctk.CTkFrame):
    def __init__(self, master, label_text: str = "Format", formats: List[ImageFormat] = None,
                 on_select: Callable[[ImageFormat], None] = None,
                 gate_results: Optional[dict] = None,  # id -> GateResult
                 width: int = 320, **kwargs):
        super().__init__(master, **kwargs)
        self.label_text = label_text
        self.all_formats = formats or FORMATS
        self.filtered = self.all_formats[:]
        self.on_select_callback = on_select
        self.gate_results = gate_results or {}
        self.selected_format: Optional[ImageFormat] = None
        self.is_open = False

        self.configure(fg_color="transparent")

        # Label
        self.label = ctk.CTkLabel(self, text=label_text, font=ctk.CTkFont(size=12, weight="bold"))
        self.label.pack(anchor="w", padx=2, pady=(0,2))

        # Main button that shows selected
        self.main_btn = ctk.CTkButton(self, text=f"Select {label_text} ▼", width=width, height=38,
                                      fg_color="#2b2b2b", hover_color="#3a3a3a",
                                      border_width=1, border_color="#444",
                                      anchor="w",
                                      command=self.toggle_dropdown)
        self.main_btn.pack(fill="x", pady=2)

        # Dropdown frame (initially hidden)
        self.dropdown_frame = ctk.CTkFrame(self, fg_color="#1e1e1e", border_width=1, border_color="#555", width=width)
        # Search entry
        self.search_entry = ctk.CTkEntry(self.dropdown_frame, placeholder_text="🔍 Search format, ext, description... e.g. 'png transparent' or 'vector'",
                                         height=36, font=ctk.CTkFont(size=12))
        self.search_entry.pack(fill="x", padx=8, pady=8)
        self.search_entry.bind("<KeyRelease>", self.on_search)

        # Scrollable list
        self.scroll = ctk.CTkScrollableFrame(self.dropdown_frame, height=300, fg_color="#1e1e1e")
        self.scroll.pack(fill="both", expand=True, padx=8, pady=(0,8))

        # Info label
        self.info_label = ctk.CTkLabel(self.dropdown_frame, text="", font=ctk.CTkFont(size=10), text_color="#aaa", wraplength=width-20, justify="left")
        self.info_label.pack(fill="x", padx=8, pady=(0,8))

        self.buttons: List[ctk.CTkButton] = []
        self.build_list(self.all_formats)

    def set_gate_results(self, gate_map: dict):
        """gate_map: format_id -> GateResult"""
        self.gate_results = gate_map
        self.build_list(self.filtered)

    def set_formats(self, formats: List[ImageFormat]):
        self.all_formats = formats
        self.filtered = formats
        self.build_list(formats)

    def toggle_dropdown(self):
        if self.is_open:
            self.close_dropdown()
        else:
            self.open_dropdown()

    def open_dropdown(self):
        self.dropdown_frame.pack(fill="both", expand=True, pady=4)
        self.is_open = True
        self.search_entry.focus()
        self.main_btn.configure(text=f"{self.main_btn.cget('text').replace(' ▼','').replace(' ▲','')} ▲")

    def close_dropdown(self):
        self.dropdown_frame.pack_forget()
        self.is_open = False
        txt = self.main_btn.cget('text').replace(' ▲',' ▼')
        if '▲' not in txt and '▼' not in txt:
            txt += ' ▼'
        else:
            txt = txt.replace(' ▲',' ▼')
        self.main_btn.configure(text=txt)

    def on_search(self, event=None):
        query = self.search_entry.get()
        if not query.strip():
            self.filtered = self.all_formats[:]
        else:
            q = query.lower()
            # fuzzy search across id, exts, name, description, category
            res = []
            for f in self.all_formats:
                hay = f"{f.id} {' '.join(f.exts)} {f.name} {f.description} {f.category}".lower()
                # simple scoring: if all tokens present
                tokens = q.split()
                if all(t in hay for t in tokens):
                    res.append(f)
            self.filtered = res
        self.build_list(self.filtered)

    def build_list(self, formats: List[ImageFormat]):
        # Clear old
        for w in self.scroll.winfo_children():
            w.destroy()
        self.buttons.clear()

        if not formats:
            lbl = ctk.CTkLabel(self.scroll, text="No formats found", text_color="#888")
            lbl.pack(pady=20)
            return

        # Group by category
        categories = {}
        for f in formats:
            categories.setdefault(f.category, []).append(f)

        cat_order = ["common_raster", "modern_raster", "animated", "vector", "legacy_raster"]
        # sort categories present
        for cat in cat_order + list(categories.keys()):
            if cat not in categories:
                continue
            flist = categories[cat]
            if not flist:
                continue
            # Category header
            header = ctk.CTkLabel(self.scroll, text=cat.replace('_',' ').upper(), font=ctk.CTkFont(size=10, weight="bold"), text_color="#888", anchor="w")
            header.pack(fill="x", padx=4, pady=(12,2))
            for fmt in sorted(flist, key=lambda x: x.name):
                gate = self.gate_results.get(fmt.id)
                status_color = "#2b2b2b"
                dot = "⚪"
                dot_color = "#666"
                if gate:
                    if gate.status == "green":
                        dot = "🟢"
                        dot_color = "#4ade80"
                        status_color = "#1a2e1a"
                    elif gate.status == "yellow":
                        dot = "🟡"
                        dot_color = "#facc15"
                        status_color = "#2e2a1a"
                    else:
                        dot = "🔴"
                        dot_color = "#f87171"
                        status_color = "#2e1a1a"

                # Button text with icon, name, exts, and dot
                ext_str = ", ".join(fmt.exts[:3])
                btn_text = f"{dot} {fmt.id.upper():<8} {fmt.name} ({ext_str})"

                btn = ctk.CTkButton(self.scroll, text=btn_text, anchor="w",
                                    fg_color=status_color, hover_color="#3a3a3a",
                                    height=32, font=ctk.CTkFont(size=11),
                                    command=lambda f=fmt: self.select_format(f))
                # Tooltip via info label on hover
                btn.bind("<Enter>", lambda e, f=fmt, g=gate: self.show_info(f, g))
                btn.pack(fill="x", pady=2)

                # If red and gate blocked, disable visually
                if gate and not gate.allowed:
                    btn.configure(state="disabled", fg_color="#2a1a1a", text_color="#666")

            # Remove category after handling
            categories[cat] = []
            if cat in cat_order:
                # prevent re-processing
                pass

        # Handle any leftover categories not in order
        for cat, flist in categories.items():
            if not flist:
                continue
            header = ctk.CTkLabel(self.scroll, text=cat.replace('_',' ').upper(), font=ctk.CTkFont(size=10, weight="bold"), text_color="#888", anchor="w")
            header.pack(fill="x", padx=4, pady=(12,2))
            for fmt in flist:
                gate = self.gate_results.get(fmt.id)
                btn_text = f"{fmt.id.upper():<8} {fmt.name}"
                btn = ctk.CTkButton(self.scroll, text=btn_text, anchor="w",
                                    fg_color="#2b2b2b", height=32,
                                    command=lambda f=fmt: self.select_format(f))
                btn.pack(fill="x", pady=2)

    def show_info(self, fmt: ImageFormat, gate: Optional[GateResult]):
        if gate:
            txt = f"{gate.reason}"
            if gate.warnings:
                txt += "\n• " + "\n• ".join(gate.warnings)
            if gate.loss_description:
                txt += f"\nLoss: {gate.loss_description}"
            self.info_label.configure(text=txt)
        else:
            self.info_label.configure(text=f"{fmt.name} - {fmt.description}")

    def select_format(self, fmt: ImageFormat):
        self.selected_format = fmt
        # Update main button
        self.main_btn.configure(text=f"{fmt.id.upper()} - {fmt.name} ▼", fg_color="#3a3a3a")
        self.close_dropdown()
        self.info_label.configure(text=f"Selected {fmt.id.upper()}: {fmt.description}")
        if self.on_select_callback:
            self.on_select_callback(fmt)

    def get_selected(self) -> Optional[ImageFormat]:
        return self.selected_format

    def set_selected_by_id(self, fid: str):
        from src.converter.formats import get_format_by_id
        fmt = get_format_by_id(fid)
        if fmt:
            self.select_format(fmt)
