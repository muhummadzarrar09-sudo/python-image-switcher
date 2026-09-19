"""
Searchable Combobox V2 - Glassmorphism + Neon + Acceptance Gate
"""

import customtkinter as ctk
from typing import List, Callable, Optional
from src.converter.formats import ImageFormat, FORMATS
from src.converter.validator import GateResult

COLORS = {
    "card": "#1a1a1a",
    "card2": "#252525",
    "border": "#2a2a2a",
    "neon": "#4ade80",
    "neon_hover": "#22c55e",
    "text_dim": "#888",
    "red": "#f87171",
    "yellow": "#facc15",
}

class SearchableFormatDropdown(ctk.CTkFrame):
    def __init__(self, master, label_text: str = "Format", formats: List[ImageFormat] = None,
                 on_select: Callable[[ImageFormat], None] = None,
                 gate_results: Optional[dict] = None,
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

        # Label with neon accent
        self.label = ctk.CTkLabel(self, text=label_text.upper(), font=ctk.CTkFont(size=10, weight="bold"), text_color=COLORS["text_dim"])
        self.label.pack(anchor="w", padx=2, pady=(0,4))

        # Main button - glass + neon border when selected
        self.main_btn = ctk.CTkButton(self, text=f"Select {label_text} ▼", width=width, height=42,
                                      fg_color=COLORS["card"], hover_color=COLORS["card2"],
                                      border_width=1, border_color=COLORS["border"],
                                      corner_radius=10,
                                      anchor="w",
                                      font=ctk.CTkFont(size=12, weight="bold"),
                                      command=self.toggle_dropdown)
        self.main_btn.pack(fill="x", pady=2)

        # Dropdown frame - glassmorphism
        self.dropdown_frame = ctk.CTkFrame(self, fg_color="#141414", border_width=1, border_color="#3a3a3a", corner_radius=12, width=width)

        # Search entry - neon focus
        self.search_entry = ctk.CTkEntry(self.dropdown_frame, placeholder_text="🔍 Search: 'png trans' 'vector' 'photo'...",
                                         height=40, font=ctk.CTkFont(size=12),
                                         fg_color=COLORS["card2"], border_color=COLORS["border"],
                                         corner_radius=10)
        self.search_entry.pack(fill="x", padx=10, pady=10)
        self.search_entry.bind("<KeyRelease>", self.on_search)

        # Scrollable list
        self.scroll = ctk.CTkScrollableFrame(self.dropdown_frame, height=320, fg_color="#141414", corner_radius=10)
        self.scroll.pack(fill="both", expand=True, padx=10, pady=(0,10))

        # Info label
        self.info_label = ctk.CTkLabel(self.dropdown_frame, text="", font=ctk.CTkFont(size=10), text_color="#aaa", wraplength=width-20, justify="left")
        self.info_label.pack(fill="x", padx=10, pady=(0,10))

        self.buttons: List[ctk.CTkButton] = []
        self.build_list(self.all_formats)

    def set_gate_results(self, gate_map: dict):
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
        self.dropdown_frame.pack(fill="both", expand=True, pady=6)
        self.is_open = True
        self.search_entry.focus()
        self.main_btn.configure(border_color=COLORS["neon"], text=f"{self.main_btn.cget('text').replace(' ▼','').replace(' ▲','')} ▲")

    def close_dropdown(self):
        self.dropdown_frame.pack_forget()
        self.is_open = False
        txt = self.main_btn.cget('text').replace(' ▲',' ▼')
        if '▲' not in txt and '▼' not in txt:
            txt += ' ▼'
        else:
            txt = txt.replace(' ▲',' ▼')
        self.main_btn.configure(border_color=COLORS["border"], text=txt)

    def on_search(self, event=None):
        query = self.search_entry.get()
        if not query.strip():
            self.filtered = self.all_formats[:]
        else:
            q = query.lower()
            res = []
            for f in self.all_formats:
                hay = f"{f.id} {' '.join(f.exts)} {f.name} {f.description} {f.category}".lower()
                tokens = q.split()
                if all(t in hay for t in tokens):
                    res.append(f)
            self.filtered = res
        self.build_list(self.filtered)

    def build_list(self, formats: List[ImageFormat]):
        for w in self.scroll.winfo_children():
            w.destroy()
        self.buttons.clear()

        if not formats:
            lbl = ctk.CTkLabel(self.scroll, text="No formats found 🔍", text_color="#888")
            lbl.pack(pady=20)
            return

        categories = {}
        for f in formats:
            categories.setdefault(f.category, []).append(f)

        cat_order = ["common_raster", "modern_raster", "animated", "vector", "legacy_raster"]

        for cat in cat_order + [c for c in categories.keys() if c not in cat_order]:
            if cat not in categories:
                continue
            flist = categories[cat]
            if not flist:
                continue

            header = ctk.CTkLabel(self.scroll, text=cat.replace('_',' ').upper(), font=ctk.CTkFont(size=10, weight="bold"), text_color=COLORS["neon"], anchor="w")
            header.pack(fill="x", padx=4, pady=(14,4))

            for fmt in sorted(flist, key=lambda x: x.name):
                gate = self.gate_results.get(fmt.id)
                status_color = COLORS["card"]
                dot = "⚪"
                if gate:
                    if gate.status == "green":
                        dot = "🟢"
                        status_color = "#1a2e1a"
                    elif gate.status == "yellow":
                        dot = "🟡"
                        status_color = "#2e2a1a"
                    else:
                        dot = "🔴"
                        status_color = "#2e1a1a"

                ext_str = ", ".join(fmt.exts[:2])
                btn_text = f"{dot} {fmt.id.upper():<7} {fmt.name} ({ext_str})"

                btn = ctk.CTkButton(self.scroll, text=btn_text, anchor="w",
                                    fg_color=status_color, hover_color="#333",
                                    height=36, corner_radius=8,
                                    font=ctk.CTkFont(size=11),
                                    command=lambda f=fmt: self.select_format(f))
                btn.bind("<Enter>", lambda e, f=fmt, g=gate: self.show_info(f, g))
                btn.pack(fill="x", pady=2)

                if gate and not gate.allowed:
                    btn.configure(state="disabled", fg_color="#1a1a1a", text_color="#555")

            categories[cat] = []

    def show_info(self, fmt: ImageFormat, gate: Optional[GateResult]):
        if gate:
            txt = f"{gate.reason}"
            if gate.warnings:
                txt += "\n• " + "\n• ".join(gate.warnings[:2])
            if gate.loss_description:
                txt += f"\nLoss: {gate.loss_description}"
            self.info_label.configure(text=txt)
        else:
            self.info_label.configure(text=f"{fmt.name} - {fmt.description}")

    def select_format(self, fmt: ImageFormat):
        self.selected_format = fmt
        # Neon border when selected
        self.main_btn.configure(text=f"{fmt.id.upper()} - {fmt.name} ▼", fg_color=COLORS["card2"], border_color=COLORS["neon"])
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
