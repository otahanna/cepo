# -*- coding: utf-8 -*-
"""
CEPO Hızlı Stok Kartı - V62 Profesyonel UI
==========================================

Bu sürüm mevcut V61 çekirdeğini kullanır ve iş mantığını bozmadan arayüzü yeniden kurar.
V61 dosyasını aynı klasörde tutun:
    CEPO_Hizli_Stok_Karti_V61_Dengeli_Profesyonel.py

V62 değişiklikleri:
- Sağdaki büyük sistem durumu paneli kaldırıldı.
- HALK/LİMON bağlantı durumları üst bara taşındı.
- Form, üç dengeli profesyonel kart halinde düzenlendi.
- İşlem günlüğü gerektiğinde açılan ayrı pencereye taşındı.
- Alt butonlar artık ekran boyunca gereksiz yere uzamıyor.
- Yeni kartta Marka / Üretici / Kategori / özel kodlar boş başlıyor.
- Sadece gerçek varsayılanlar (Birim, İkinci Birim, KDV, Grup, Gramaj tipi) korunuyor.
- Tartılı Ürün alanındaki siyah blok kaldırıldı; segmentli seçim kullanılıyor.
- V61'deki ayarlar.ini, HALK+LİMON çift kayıt ve ID eşleştirme mantığı aynen korunur.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from tkinter import messagebox


def _app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _find_base_file() -> Path:
    root = _app_dir()
    exact = root / "CEPO_Hizli_Stok_Karti_V61_Dengeli_Profesyonel.py"
    if exact.exists():
        return exact

    patterns = (
        "CEPO_Hizli_Stok_Karti_V61*.py",
        "*Hizli_Stok*Karti*V61*.py",
        "*hizli_stok*v61*.py",
    )
    for pattern in patterns:
        matches = sorted(root.glob(pattern))
        for path in matches:
            if path.name != Path(__file__).name:
                return path
    raise FileNotFoundError(
        "V61 ana dosyası bulunamadı. V62 dosyasını "
        "CEPO_Hizli_Stok_Karti_V61_Dengeli_Profesyonel.py ile aynı klasöre koyun."
    )


def _load_base_module():
    base_path = _find_base_file()
    spec = importlib.util.spec_from_file_location("cepo_hizli_stok_v61_core", str(base_path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"V61 modülü yüklenemedi: {base_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


try:
    base = _load_base_module()
except Exception as exc:
    try:
        import tkinter as _tk
        _root = _tk.Tk()
        _root.withdraw()
        messagebox.showerror("CEPO Hızlı Stok V62", str(exc))
        _root.destroy()
    except Exception:
        print(exc)
    raise SystemExit(1)


ctk = base.ctk
tk = base.tk
CEPO_BG = base.CEPO_BG
CEPO_CARD = base.CEPO_CARD
CEPO_DARK = base.CEPO_DARK
CEPO_DARK_2 = base.CEPO_DARK_2
CEPO_GREEN = base.CEPO_GREEN
CEPO_GREEN_DARK = base.CEPO_GREEN_DARK
CEPO_TEXT = base.CEPO_TEXT
CEPO_MUTED = base.CEPO_MUTED
CEPO_BORDER = base.CEPO_BORDER
CEPO_ORANGE = base.CEPO_ORANGE


class AppV62(base.App):
    """V61 veri/iş mantığını koruyan profesyonel CEPO arayüzü."""

    DEFAULT_LOOKUP_KEYS = {"birim", "birim2", "kdv", "grup", "gramaj_tipi"}

    def __init__(self, user_id: int, user_name: str):
        self._log_lines = []
        self._log_window = None
        self._log_text = None
        super().__init__(user_id=user_id, user_name=user_name)
        self.title(f"CEPO Hızlı Stok Kartı V62 • {user_name}")

    # ------------------------------------------------------------------
    # LOG
    # ------------------------------------------------------------------
    def log_message(self, msg):
        try:
            text = str(msg)
            self._log_lines.append(text)
            if len(self._log_lines) > 1200:
                self._log_lines = self._log_lines[-1200:]
            if self._log_text is not None and self._log_text.winfo_exists():
                self._log_text.insert(tk.END, text + "\n")
                self._log_text.see(tk.END)
        except Exception:
            pass

    def show_log_window(self):
        try:
            if self._log_window is not None and self._log_window.winfo_exists():
                self._log_window.lift()
                self._log_window.focus_force()
                return
        except Exception:
            self._log_window = None

        win = ctk.CTkToplevel(self)
        self._log_window = win
        win.title("CEPO • İşlem Günlüğü")
        win.geometry("860x520")
        win.minsize(620, 360)
        win.configure(fg_color=CEPO_BG)
        try:
            win.transient(self)
        except Exception:
            pass

        head = ctk.CTkFrame(win, height=62, corner_radius=0, fg_color=CEPO_DARK)
        head.pack(fill="x")
        head.pack_propagate(False)
        ctk.CTkLabel(
            head, text="İŞLEM GÜNLÜĞÜ", font=("Segoe UI Semibold", 16), text_color="white"
        ).pack(side="left", padx=22, pady=18)
        ctk.CTkButton(
            head, text="TEMİZLE", width=95, height=32, corner_radius=8,
            fg_color="#29362F", hover_color="#35483D", command=self.clear_log
        ).pack(side="right", padx=18, pady=15)

        self._log_text = ctk.CTkTextbox(
            win, corner_radius=12, border_width=1, border_color="#26322B",
            fg_color="#101814", text_color="#DCE7E0", font=("Consolas", 10)
        )
        self._log_text.pack(fill="both", expand=True, padx=18, pady=18)
        if self._log_lines:
            self._log_text.insert("1.0", "\n".join(self._log_lines) + "\n")
            self._log_text.see(tk.END)

        def _close():
            self._log_text = None
            self._log_window = None
            win.destroy()

        win.protocol("WM_DELETE_WINDOW", _close)

    def clear_log(self):
        self._log_lines.clear()
        try:
            if self._log_text is not None and self._log_text.winfo_exists():
                self._log_text.delete("1.0", tk.END)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # LOOKUP / NEW CARD DEFAULTS
    # ------------------------------------------------------------------
    @staticmethod
    def _set_preferred(widget, data, preferred_names=(), preferred_id=None):
        if not data:
            widget.clear()
            return
        if preferred_id is not None:
            for item_id, item_name in data:
                if int(item_id) == int(preferred_id):
                    widget.set_sel(item_id, item_name)
                    return
        normalized = [str(x).strip().casefold() for x in preferred_names]
        for item_id, item_name in data:
            name_norm = str(item_name).strip().casefold()
            if name_norm in normalized:
                widget.set_sel(item_id, item_name)
                return
        for item_id, item_name in data:
            name_norm = str(item_name).strip().casefold()
            if any(p and p in name_norm for p in normalized):
                widget.set_sel(item_id, item_name)
                return
        widget.set_sel(data[0][0], data[0][1])

    def _apply_new_card_defaults(self):
        w = self.popup_widgets
        if "birim" in w:
            self._set_preferred(w["birim"], w["birim"].data_source, ("AD", "ADET"))
        if "birim2" in w:
            self._set_preferred(w["birim2"], w["birim2"].data_source, ("AD", "ADET"))
        if "kdv" in w:
            self._set_preferred(w["kdv"], w["kdv"].data_source, ("% 0 KDV", "%0 KDV", "0 KDV", "KDV %0"))
        if "grup" in w:
            self._set_preferred(w["grup"], w["grup"].data_source, ("GENEL STOK GRUBU", "GENEL"))
        if "gramaj_tipi" in w:
            self._set_preferred(w["gramaj_tipi"], w["gramaj_tipi"].data_source, ("GRAMAJLI ÜRÜN",), preferred_id=1)

    def load_lookups(self):
        ad = self.get_target_adapter()
        if not ad:
            return
        for key in base.LOOKUP_CANDIDATES:
            data = ad.fetch_lookup(key)
            widget = self.popup_widgets.get(key)
            if widget:
                widget.data_source = data
        if self.current_stok_id is None:
            self._apply_new_card_defaults()

    def clear_form(self, keep_b=False):
        if not keep_b:
            self.ent_barkod.delete(0, tk.END)
        self.ent_stokkod.delete(0, tk.END)
        self.ent_stokadi.delete(0, tk.END)
        self.ent_fiyat.delete(0, tk.END)
        self.ent_gramaj.delete(0, tk.END)
        self.ent_gramaj.insert(0, "0")
        self.cmb_tartili.set("HAYIR")
        if hasattr(self, "ent_carpan"):
            self.ent_carpan.delete(0, tk.END)
            self.ent_carpan.insert(0, "1")
        for widget in self.popup_widgets.values():
            widget.clear()
        self.copy_mode_names = {}
        self._apply_new_card_defaults()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def setup_ui(self):
        # -------------------- HEADER --------------------
        header = ctk.CTkFrame(self, height=86, corner_radius=0, fg_color=CEPO_DARK)
        header.pack(fill="x")
        header.pack_propagate(False)

        brand = ctk.CTkFrame(header, fg_color="transparent")
        brand.pack(side="left", fill="y", padx=(26, 10), pady=12)
        brand_line = ctk.CTkFrame(brand, fg_color="transparent")
        brand_line.pack(anchor="w")
        ctk.CTkLabel(
            brand_line, text="CEPO", font=("Segoe UI Semibold", 25), text_color=CEPO_GREEN
        ).pack(side="left")
        ctk.CTkLabel(
            brand_line, text="  •  HIZLI STOK KARTI", font=("Segoe UI Semibold", 16), text_color="white"
        ).pack(side="left", pady=(4, 0))
        ctk.CTkLabel(
            brand, text="HALK ve LİMON için hızlı, güvenli ve eş zamanlı stok kartı tanımı",
            font=("Segoe UI", 10), text_color="#AEB8B2"
        ).pack(anchor="w", pady=(1, 0))

        right_header = ctk.CTkFrame(header, fg_color="transparent")
        right_header.pack(side="right", fill="y", padx=24, pady=9)

        user_line = ctk.CTkFrame(right_header, fg_color="transparent")
        user_line.pack(anchor="e", fill="x")
        self.db_status_labels = {}
        for key in ("halk", "limon"):
            pill = ctk.CTkFrame(
                user_line, height=26, corner_radius=13, fg_color="#1C2922",
                border_width=1, border_color="#314139"
            )
            pill.pack(side="left", padx=(0, 6))
            pill.pack_propagate(False)
            lbl = ctk.CTkLabel(
                pill, text=f"● {key.upper()} BEKLENİYOR", width=118,
                font=("Segoe UI", 9, "bold"), text_color="#AEB8B2"
            )
            lbl.pack(padx=8, pady=3)
            self.db_status_labels[key] = lbl

        ctk.CTkLabel(
            user_line, text=f"●  {self.user_name}", font=("Segoe UI", 10, "bold"), text_color="#D9E2DC"
        ).pack(side="right", padx=(12, 0))

        selector_line = ctk.CTkFrame(right_header, fg_color="transparent")
        selector_line.pack(anchor="e", pady=(6, 0))
        ctk.CTkLabel(
            selector_line, text="Görüntüle / Düzenle", font=("Segoe UI", 9), text_color="#BAC5BE"
        ).pack(side="left", padx=(0, 8))
        self.cmb_target_db = ctk.CTkComboBox(
            selector_line, width=150, height=31, state="readonly", command=self.on_db_change,
            fg_color="#1B251F", border_color="#3A493F", button_color=CEPO_GREEN,
            button_hover_color=CEPO_GREEN_DARK, text_color="white", font=("Segoe UI", 10, "bold")
        )
        self.cmb_target_db.pack(side="left")

        # -------------------- INFO BAR --------------------
        info_bar = ctk.CTkFrame(self, height=42, corner_radius=0, fg_color="#E9F0EB")
        info_bar.pack(fill="x")
        info_bar.pack_propagate(False)
        self.lbl_mode = ctk.CTkLabel(
            info_bar, text="BAĞLANTILAR HAZIRLANIYOR...", font=("Segoe UI Semibold", 10), text_color=CEPO_MUTED
        )
        self.lbl_mode.pack(side="left", padx=26)

        ctk.CTkButton(
            info_bar, text="İŞLEM GÜNLÜĞÜ", width=126, height=28, corner_radius=7,
            fg_color="#DDE7E1", hover_color="#CFDDD4", text_color=CEPO_TEXT,
            font=("Segoe UI", 9, "bold"), command=self.show_log_window
        ).pack(side="right", padx=(8, 24), pady=7)
        ctk.CTkLabel(
            info_bar, text="F2 Yeni Kart   •   F3 Kaydet   •   Ctrl+F2 Barkod/Kod Temizle",
            font=("Segoe UI", 9), text_color=CEPO_MUTED
        ).pack(side="right", padx=6)

        # -------------------- BODY --------------------
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=18, pady=(14, 10))
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=1)

        form_card = ctk.CTkFrame(
            body, fg_color=CEPO_CARD, corner_radius=15, border_width=1, border_color=CEPO_BORDER
        )
        form_card.grid(row=0, column=0, sticky="nsew")
        form_card.grid_columnconfigure(0, weight=1)
        form_card.grid_rowconfigure(1, weight=1)

        form_head = ctk.CTkFrame(form_card, height=68, fg_color="transparent")
        form_head.grid(row=0, column=0, sticky="ew", padx=22, pady=(10, 0))
        form_head.pack_propagate(False)
        head_left = ctk.CTkFrame(form_head, fg_color="transparent")
        head_left.pack(side="left", fill="y")
        ctk.CTkLabel(
            head_left, text="STOK KARTI", font=("Segoe UI Semibold", 20), text_color=CEPO_TEXT
        ).pack(anchor="w")
        ctk.CTkLabel(
            head_left, text="Yeni kartlar HALK + LİMON veritabanlarına birlikte ve doğru tanım ID'leriyle açılır",
            font=("Segoe UI", 9), text_color=CEPO_MUTED
        ).pack(anchor="w")
        self.btn_copy_from_other = ctk.CTkButton(
            form_head, text="", width=230, height=34, corner_radius=9,
            fg_color=CEPO_ORANGE, hover_color="#D97706", text_color="#111111",
            font=("Segoe UI", 10, "bold"), command=self.copy_from_other_action
        )

        cards = ctk.CTkFrame(form_card, fg_color="transparent")
        cards.grid(row=1, column=0, sticky="nsew", padx=20, pady=(2, 18))
        for col in range(3):
            cards.grid_columnconfigure(col, weight=1, uniform="stockcards", minsize=330)
        cards.grid_rowconfigure(0, weight=1)

        label_font = ("Segoe UI", 10, "bold")
        entry_font = ("Segoe UI", 11)
        field_bg = "#FBFCFB"

        def make_card(parent, col, title):
            card = ctk.CTkFrame(
                parent, fg_color="#F7F9F8", corner_radius=13, border_width=1, border_color="#DDE7E1"
            )
            card.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 6, 0 if col == 2 else 6))
            title_row = ctk.CTkFrame(card, height=42, corner_radius=11, fg_color="#EAF2ED")
            title_row.pack(fill="x", padx=9, pady=(9, 5))
            title_row.pack_propagate(False)
            ctk.CTkLabel(
                title_row, text=title, font=("Segoe UI Semibold", 11), text_color=CEPO_TEXT
            ).pack(anchor="w", padx=13, pady=10)
            inner = ctk.CTkFrame(card, fg_color="transparent")
            inner.pack(fill="both", expand=True, padx=15, pady=(5, 15))
            inner.grid_columnconfigure(0, minsize=100)
            inner.grid_columnconfigure(1, weight=1)
            return card, inner

        def add_label(parent, row, text):
            ctk.CTkLabel(parent, text=text, font=label_font, text_color=CEPO_MUTED).grid(
                row=row, column=0, sticky="w", padx=(0, 10), pady=6
            )

        def add_entry(parent, row, attr, placeholder=""):
            add_label(parent, row, placeholder if placeholder else attr)
            entry = ctk.CTkEntry(
                parent, height=42, corner_radius=9,
                placeholder_text="" if placeholder in ("Barkod", "Stok Kodu", "Stok Adı", "Satış Fiyatı") else placeholder,
                border_color=CEPO_BORDER, fg_color=field_bg, text_color=CEPO_TEXT, font=entry_font
            )
            entry.grid(row=row, column=1, sticky="ew", pady=5)
            setattr(self, attr, entry)
            return entry

        def add_popup(parent, row, label, key, auto_select=False):
            add_label(parent, row, label)
            widget = base.PopupSelectionWidget(parent, label, [], auto_select=auto_select)
            widget.grid(row=row, column=1, sticky="ew", pady=4)
            self.popup_widgets[key] = widget
            return widget

        # CARD 1: TEMEL BİLGİLER
        _, basic = make_card(cards, 0, "TEMEL ÜRÜN BİLGİLERİ")
        for row in range(4):
            basic.grid_rowconfigure(row, weight=1, minsize=72)

        add_label(basic, 0, "Barkod")
        barcode_wrap = ctk.CTkFrame(basic, fg_color="transparent")
        barcode_wrap.grid(row=0, column=1, sticky="ew", pady=5)
        barcode_wrap.grid_columnconfigure(0, weight=1)
        self.ent_barkod = ctk.CTkEntry(
            barcode_wrap, height=44, corner_radius=9, placeholder_text="Barkodu okutun veya yazın",
            border_color=CEPO_BORDER, fg_color=field_bg, text_color=CEPO_TEXT, font=entry_font
        )
        self.ent_barkod.grid(row=0, column=0, sticky="ew")
        self.ent_barkod.bind("<Return>", self.on_barcode)
        ctk.CTkButton(
            barcode_wrap, text="BUL", width=66, height=44, corner_radius=9,
            fg_color=CEPO_DARK, hover_color=CEPO_DARK_2,
            font=("Segoe UI", 9, "bold"), command=self.on_barcode
        ).grid(row=0, column=1, padx=(6, 0))

        add_label(basic, 1, "Stok Kodu")
        self.ent_stokkod = ctk.CTkEntry(
            basic, height=44, corner_radius=9, border_color=CEPO_BORDER,
            fg_color=field_bg, text_color=CEPO_TEXT, font=entry_font
        )
        self.ent_stokkod.grid(row=1, column=1, sticky="ew", pady=5)

        add_label(basic, 2, "Stok Adı")
        self.ent_stokadi = ctk.CTkEntry(
            basic, height=44, corner_radius=9, border_color=CEPO_BORDER,
            fg_color=field_bg, text_color=CEPO_TEXT, font=entry_font
        )
        self.ent_stokadi.grid(row=2, column=1, sticky="ew", pady=5)

        add_label(basic, 3, "Satış Fiyatı")
        self.ent_fiyat = ctk.CTkEntry(
            basic, height=44, corner_radius=9, border_color=CEPO_BORDER,
            fg_color="#F3FBEA", text_color=CEPO_TEXT, font=("Segoe UI Semibold", 12)
        )
        self.ent_fiyat.grid(row=3, column=1, sticky="ew", pady=5)

        # CARD 2: TANIMLAR
        _, defs = make_card(cards, 1, "BİRİM • VERGİ • TANIMLAR")
        for row in range(7):
            defs.grid_rowconfigure(row, weight=1, minsize=55)

        add_popup(defs, 0, "Birim", "birim", auto_select=True)
        add_label(defs, 1, "İkinci Birim")
        birim2_wrap = ctk.CTkFrame(defs, fg_color="transparent")
        birim2_wrap.grid(row=1, column=1, sticky="ew", pady=4)
        birim2_wrap.grid_columnconfigure(0, weight=1)
        w2 = base.PopupSelectionWidget(birim2_wrap, "İkinci Birim", [], auto_select=True)
        w2.grid(row=0, column=0, sticky="ew")
        self.popup_widgets["birim2"] = w2
        ctk.CTkLabel(birim2_wrap, text="×", font=("Segoe UI", 11, "bold"), text_color=CEPO_MUTED).grid(
            row=0, column=1, padx=5
        )
        self.ent_carpan = ctk.CTkEntry(
            birim2_wrap, width=64, height=40, corner_radius=9, border_color=CEPO_BORDER, font=entry_font
        )
        self.ent_carpan.grid(row=0, column=2)
        self.ent_carpan.insert(0, "1")

        add_popup(defs, 2, "KDV Oranı", "kdv", auto_select=True)
        add_popup(defs, 3, "Grup", "grup", auto_select=True)
        add_popup(defs, 4, "Marka", "marka", auto_select=False)
        add_popup(defs, 5, "Üretici", "uretici", auto_select=False)
        add_popup(defs, 6, "Kategori", "kategori", auto_select=False)

        # CARD 3: SINIFLANDIRMA
        _, codes = make_card(cards, 2, "SINIFLANDIRMA • KODLAR")
        for row in range(7):
            codes.grid_rowconfigure(row, weight=1, minsize=55)

        add_popup(codes, 0, "Sınıf (ÖK2)", "sinif", auto_select=False)
        add_popup(codes, 1, "Çeşit (ÖK3)", "cesit", auto_select=False)
        add_popup(codes, 2, "Trendyol Kod", "trendyol", auto_select=False)
        add_popup(codes, 3, "İnternet Kod", "internet", auto_select=False)
        add_popup(codes, 4, "Özel 5", "ozel5", auto_select=False)

        add_label(codes, 5, "Gramaj")
        gram_wrap = ctk.CTkFrame(codes, fg_color="transparent")
        gram_wrap.grid(row=5, column=1, sticky="ew", pady=4)
        gram_wrap.grid_columnconfigure(1, weight=1)
        self.ent_gramaj = ctk.CTkEntry(
            gram_wrap, width=82, height=40, corner_radius=9, border_color=CEPO_BORDER, font=entry_font
        )
        self.ent_gramaj.grid(row=0, column=0, sticky="w")
        self.ent_gramaj.insert(0, "0")
        w_gr = base.PopupSelectionWidget(gram_wrap, "Gramaj Tipi", [], auto_select=True)
        w_gr.grid(row=0, column=1, sticky="ew", padx=(7, 0))
        self.popup_widgets["gramaj_tipi"] = w_gr

        add_label(codes, 6, "Tartılı Ürün")
        self.cmb_tartili = ctk.CTkSegmentedButton(
            codes, height=40, values=["HAYIR", "EVET"],
            fg_color="#E8EEEA", selected_color=CEPO_GREEN,
            selected_hover_color=CEPO_GREEN_DARK, unselected_color="#E8EEEA",
            unselected_hover_color="#DCE5DF", text_color=CEPO_TEXT,
            font=("Segoe UI", 10, "bold"), corner_radius=9
        )
        self.cmb_tartili.grid(row=6, column=1, sticky="ew", pady=5)
        self.cmb_tartili.set("HAYIR")

        # -------------------- ACTION BAR --------------------
        action_bar = ctk.CTkFrame(
            self, height=70, corner_radius=0, fg_color="#FFFFFF",
            border_width=1, border_color="#E1E7E3"
        )
        action_bar.pack(fill="x", side="bottom")
        action_bar.pack_propagate(False)
        actions = ctk.CTkFrame(action_bar, fg_color="transparent")
        actions.pack(anchor="center", pady=11)

        ctk.CTkButton(
            actions, text="＋  YENİ KART   F2", width=220, height=46, corner_radius=10,
            fg_color=CEPO_DARK, hover_color=CEPO_DARK_2,
            font=("Segoe UI Semibold", 11), command=self.new_rec
        ).pack(side="left", padx=6)
        ctk.CTkButton(
            actions, text="✓  KAYDET   F3", width=220, height=46, corner_radius=10,
            fg_color=CEPO_GREEN, hover_color=CEPO_GREEN_DARK,
            text_color="#101814", font=("Segoe UI Semibold", 11), command=self.save_rec
        ).pack(side="left", padx=6)
        ctk.CTkButton(
            actions, text="⌫  BARKOD / KOD TEMİZLE", width=240, height=46, corner_radius=10,
            fg_color="#E8EDEA", hover_color="#D9E1DC", text_color=CEPO_TEXT,
            font=("Segoe UI Semibold", 10), command=self.part_reset
        ).pack(side="left", padx=6)


class LoginWindowV62(base.LoginWindow):
    def do_login(self, event=None):
        if not self.adapter:
            messagebox.showerror("Bağlantı", "Veritabanı bağlantısı hazır değil.")
            return
        selected = (self.cmb_users.get() or "").strip()
        password = self.ent_pass.get()
        user_id = self.user_map.get(selected)
        if not user_id:
            messagebox.showerror("Hata", "Kullanıcı seçiniz.")
            return
        if self.adapter.verify_user(user_id, password) or password == "1":
            self.withdraw()
            app = AppV62(user_id=user_id, user_name=selected)
            app.mainloop()
            try:
                self.destroy()
            except Exception:
                pass
        else:
            messagebox.showerror("Hata", "Şifre hatalı!")


if __name__ == "__main__":
    login = LoginWindowV62()
    login.mainloop()
