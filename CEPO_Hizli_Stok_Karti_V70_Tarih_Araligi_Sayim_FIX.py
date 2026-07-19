# -*- coding: utf-8 -*-
"""
CEPO Hızlı Stok Kartı V70

V69 üzerine eklenenler:
- Stok Hareketleri sekmesine Başlangıç / Bitiş tarih aralığı seçimi.
- Tarihler gün + Türkçe ay adı + yıl olarak seçilir.
- Varsayılan dönem: Son 30 Gün.
- Hızlı dönem butonları: Son 30 Gün, Bu Yıl, Tüm Tarihler.
- Tarih aralığı SQL sorgusuna uygulanır; yalnız ekranda filtreleme yapılmaz.
- TBL_STOK_HAREKET hareketlerinde daha fazla kayıt okunur.
- Sayım hareketleri yalnız stok hareketinden beklenmez; TBL_SAYIM_MAIN ve ilişkili sayım detay
  tabloları dinamik olarak keşfedilerek seçili ürünün sayım kayıtları hareket listesine eklenir.
- HALK + LİMON stokları, bakiye/maliyet/tutar ve Google görsel düzeltmeleri V69'dan korunur.

KULLANIM:
CEPO_Hizli_Stok_Karti_V65_Referans_Profesyonel.py ile aynı klasöre koyup V70'i çalıştırın.
V69/V68/V67 yoksa internetten otomatik indirilmeye çalışılır.
"""

from __future__ import annotations

import os
import sys
import re
import threading
import importlib.util
import urllib.request
import datetime
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
V69_FILE = "CEPO_Hizli_Stok_Karti_V69_Limon_Stok_Google_Gorsel_FIX.py"
V69_PATH = os.path.join(HERE, V69_FILE)
V69_URL = "https://raw.githubusercontent.com/otahanna/cepo/main/CEPO_Hizli_Stok_Karti_V69_Limon_Stok_Google_Gorsel_FIX.py"


def _v70_download(url: str, path: str) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 CEPO-Hizli-Stok-V70"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
    with open(path, "wb") as f:
        f.write(data)


if not os.path.isfile(V69_PATH):
    try:
        _v70_download(V69_URL, V69_PATH)
    except Exception as exc:
        raise SystemExit("V69 yardımcı dosyası indirilemedi:\n" + str(exc))

spec = importlib.util.spec_from_file_location("cepo_hizli_stok_v69_base", V69_PATH)
if spec is None or spec.loader is None:
    raise SystemExit("V69 modülü yüklenemedi.")
v69 = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = v69
spec.loader.exec_module(v69)

v68 = v69.v68
v67 = v69.v67
base = v69.base
base.APP_TITLE = "CEPO Hızlı Stok Kartı V70"

TR_MONTHS = [
    "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
]
TR_MONTH_TO_NUM = {name: i + 1 for i, name in enumerate(TR_MONTHS)}


# =============================================================================
# TARİH SEÇİCİ ARAYÜZÜ
# =============================================================================
_ORIG_SETUP_UI_V70 = base.App.setup_ui


def _v70_set_selector_date(self, prefix: str, d: date) -> None:
    try:
        getattr(self, f"cmb_v70_{prefix}_day").set(f"{d.day:02d}")
        getattr(self, f"cmb_v70_{prefix}_month").set(TR_MONTHS[d.month - 1])
        getattr(self, f"cmb_v70_{prefix}_year").set(str(d.year))
    except Exception:
        pass


def _v70_read_selector_date(self, prefix: str) -> date:
    day = int(getattr(self, f"cmb_v70_{prefix}_day").get())
    month_name = str(getattr(self, f"cmb_v70_{prefix}_month").get() or "").strip()
    year = int(getattr(self, f"cmb_v70_{prefix}_year").get())
    month = TR_MONTH_TO_NUM.get(month_name)
    if not month:
        raise ValueError("Ay seçimi geçersiz.")
    return date(year, month, day)


def _v70_period_text(start: Optional[date], end: Optional[date]) -> str:
    if start is None and end is None:
        return "Tüm Tarihler"

    def fmt(d: date) -> str:
        return f"{d.day:02d} {TR_MONTHS[d.month - 1]} {d.year}"

    if start and end:
        return f"{fmt(start)} – {fmt(end)}"
    if start:
        return f"{fmt(start)} sonrası"
    return f"{fmt(end)} öncesi"


def _v70_reload_dashboard_without_image(self) -> None:
    try:
        barcode = (self.ent_barkod.get() or "").strip()
    except Exception:
        barcode = ""
    if not barcode:
        return
    try:
        self._v69_dashboard_stock_code = (self.ent_stokkod.get() or "").strip()
    except Exception:
        self._v69_dashboard_stock_code = ""
    self._dashboard_token = int(getattr(self, "_dashboard_token", 0)) + 1
    token = self._dashboard_token
    try:
        self.lbl_dashboard_info.configure(text=f"{barcode} için seçili tarih aralığı yükleniyor...")
        self.lbl_dashboard_state.configure(text="Stok hareketleri yenileniyor...")
    except Exception:
        pass
    threading.Thread(target=self._dashboard_worker, args=(barcode, token), daemon=True).start()


def _v70_apply_selected_period(self) -> None:
    try:
        start = _v70_read_selector_date(self, "from")
        end = _v70_read_selector_date(self, "to")
        if start > end:
            start, end = end, start
            _v70_set_selector_date(self, "from", start)
            _v70_set_selector_date(self, "to", end)
        self._v70_start_date = start
        self._v70_end_date = end
        try:
            self.lbl_v70_period.configure(text=_v70_period_text(start, end))
        except Exception:
            pass
        _v70_reload_dashboard_without_image(self)
    except Exception as exc:
        try:
            base.messagebox.showerror("Tarih Aralığı", f"Geçerli bir tarih seçin.\n\n{exc}", parent=self)
        except Exception:
            pass


def _v70_quick_period(self, mode: str) -> None:
    today = date.today()
    if mode == "30":
        start, end = today - timedelta(days=29), today
    elif mode == "year":
        start, end = date(today.year, 1, 1), today
    else:
        self._v70_start_date = None
        self._v70_end_date = None
        try:
            self.lbl_v70_period.configure(text="Tüm Tarihler")
        except Exception:
            pass
        _v70_reload_dashboard_without_image(self)
        return

    _v70_set_selector_date(self, "from", start)
    _v70_set_selector_date(self, "to", end)
    self._v70_start_date = start
    self._v70_end_date = end
    try:
        self.lbl_v70_period.configure(text=_v70_period_text(start, end))
    except Exception:
        pass
    _v70_reload_dashboard_without_image(self)


def _v70_setup_ui(self):
    _ORIG_SETUP_UI_V70(self)

    today = date.today()
    start_default = today - timedelta(days=29)
    self._v70_start_date: Optional[date] = start_default
    self._v70_end_date: Optional[date] = today

    try:
        move_top = self.movement_filter.master
        tab_moves = move_top.master
        move_wrap = self.movement_tree.master

        bar = base.ctk.CTkFrame(
            tab_moves,
            fg_color="#F4F7F5",
            corner_radius=8,
            border_width=1,
            border_color="#DDE5E0",
        )
        bar.pack(fill="x", padx=2, pady=(0, 5), before=move_wrap)

        base.ctk.CTkLabel(
            bar, text="TARİH ARALIĞI", font=("Segoe UI Semibold", 8), text_color=base.CEPO_MUTED
        ).pack(side="left", padx=(10, 8), pady=7)

        days = [f"{i:02d}" for i in range(1, 32)]
        current_year = today.year
        years = [str(y) for y in range(current_year + 2, current_year - 12, -1)]

        def make_date_group(prefix: str, title: str):
            holder = base.ctk.CTkFrame(bar, fg_color="transparent")
            holder.pack(side="left", padx=(0, 8), pady=5)
            base.ctk.CTkLabel(holder, text=title, font=("Segoe UI Semibold", 8), text_color=base.CEPO_TEXT).pack(side="left", padx=(0, 4))

            day_cb = base.ctk.CTkComboBox(holder, values=days, width=58, height=28, state="readonly", font=("Segoe UI", 8))
            day_cb.pack(side="left", padx=1)
            month_cb = base.ctk.CTkComboBox(holder, values=TR_MONTHS, width=94, height=28, state="readonly", font=("Segoe UI", 8))
            month_cb.pack(side="left", padx=1)
            year_cb = base.ctk.CTkComboBox(holder, values=years, width=74, height=28, state="readonly", font=("Segoe UI", 8))
            year_cb.pack(side="left", padx=1)

            setattr(self, f"cmb_v70_{prefix}_day", day_cb)
            setattr(self, f"cmb_v70_{prefix}_month", month_cb)
            setattr(self, f"cmb_v70_{prefix}_year", year_cb)

        make_date_group("from", "Başlangıç")
        make_date_group("to", "Bitiş")

        _v70_set_selector_date(self, "from", start_default)
        _v70_set_selector_date(self, "to", today)

        base.ctk.CTkButton(
            bar, text="UYGULA", width=66, height=28, corner_radius=7,
            fg_color=base.CEPO_GREEN, hover_color=base.CEPO_GREEN_DARK,
            text_color="#101814", font=("Segoe UI Semibold", 8),
            command=lambda: _v70_apply_selected_period(self),
        ).pack(side="left", padx=(2, 5))

        base.ctk.CTkButton(
            bar, text="SON 30 GÜN", width=82, height=28, corner_radius=7,
            fg_color="#E7EEE9", hover_color="#D8E4DC", text_color=base.CEPO_TEXT,
            font=("Segoe UI Semibold", 8), command=lambda: _v70_quick_period(self, "30"),
        ).pack(side="left", padx=2)
        base.ctk.CTkButton(
            bar, text="BU YIL", width=58, height=28, corner_radius=7,
            fg_color="#E7EEE9", hover_color="#D8E4DC", text_color=base.CEPO_TEXT,
            font=("Segoe UI Semibold", 8), command=lambda: _v70_quick_period(self, "year"),
        ).pack(side="left", padx=2)
        base.ctk.CTkButton(
            bar, text="TÜMÜ", width=54, height=28, corner_radius=7,
            fg_color="#E7EEE9", hover_color="#D8E4DC", text_color=base.CEPO_TEXT,
            font=("Segoe UI Semibold", 8), command=lambda: _v70_quick_period(self, "all"),
        ).pack(side="left", padx=2)

        self.lbl_v70_period = base.ctk.CTkLabel(
            bar, text=_v70_period_text(start_default, today),
            font=("Segoe UI", 8), text_color=base.CEPO_MUTED,
        )
        self.lbl_v70_period.pack(side="right", padx=10)
    except Exception as exc:
        try:
            base.debug_print(f"V70 tarih seçici oluşturulamadı: {exc}")
        except Exception:
            pass


base.App.setup_ui = _v70_setup_ui


# =============================================================================
# HAREKET SORGUSU - SEÇİLİ TARİH ARALIĞI SQL'DE UYGULANIR
# =============================================================================
def _v70_date_where(alias: str, col: str, start: Optional[date], end: Optional[date]) -> Tuple[str, List[Any]]:
    clauses: List[str] = []
    params: List[Any] = []
    if start:
        clauses.append(f"{alias}.{col} >= ?")
        params.append(datetime.datetime(start.year, start.month, start.day))
    if end:
        next_day = end + timedelta(days=1)
        clauses.append(f"{alias}.{col} < ?")
        params.append(datetime.datetime(next_day.year, next_day.month, next_day.day))
    return (" AND " + " AND ".join(clauses)) if clauses else "", params


def _v70_movement_category(adapter, type_id: Any, type_name: str, desc: str) -> str:
    category = adapter._movement_category(type_id, type_name, desc)
    if category != "Diğer":
        return category
    txt = f"{type_name or ''} {desc or ''}".upper()
    txt = txt.translate(str.maketrans({"İ":"I", "Ş":"S", "Ğ":"G", "Ü":"U", "Ö":"O", "Ç":"C"}))
    if any(x in txt for x in ("SAYIM", "ENVANTER", "STOK DUZELT", "STOK SAY")):
        return "Sayım"
    return category


def _v70_load_stock_movements(adapter, stock_id: int, db_name: str, start: Optional[date], end: Optional[date]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not adapter.cn or not stock_id:
        return out

    hcols = adapter._table_cols(base.HAREKET_TABLE)
    h_stok = adapter._first_existing(hcols, ["STOKID", "STOKKARTID", "STOK_ID"])
    h_date = adapter._first_existing(hcols, ["BELGETARIHI", "TARIH", "ISLEMTARIHI", "CREATEDATE"])
    h_qty = adapter._first_existing(hcols, ["MIKTAR", "ADET", "MIK", "QTY", "MIKTAR1"])
    h_type = adapter._first_existing(hcols, ["HAREKETTIPID", "TIPID", "HAREKETTIPI"])
    h_amount = adapter._first_existing(hcols, ["NETTUTAR", "TOPLAMTUTAR", "GENELTOPLAM", "TUTAR", "TUTAR1"])
    h_loc = adapter._first_existing(hcols, ["DEPOID", "SUBEID", "MAGAZAID"])
    h_doc = adapter._first_existing(hcols, ["BELGEKODU", "BELGENO", "FISNO", "EVRAKNO"])
    h_desc = adapter._first_existing(hcols, ["ACIKLAMA", "NOTLAR", "NOT", "DESCRIPTION"])
    h_cari = adapter._first_existing(hcols, ["CARIID", "TEDARIKCIID", "MUSTERI_ID"])
    if not h_stok or not h_date or not h_qty:
        return out

    depo_map = adapter._id_name_map(base.DEPO_TABLE, ["DEPOADI", "DEPO_ADI", "ACIKLAMA", "ADI", "ISIM", "TANIM"])
    sube_map = adapter._id_name_map(base.SUBE_TABLE, ["SUBEADI", "SUBE_ADI", "ACIKLAMA", "ADI", "ISIM", "TANIM"])
    cari_map = adapter._id_name_map(base.CARI_TABLE, ["CARIADI", "UNVANI", "UNVAN", "ADI", "ISIM"])

    tip_cols = adapter._table_cols(base.HAREKET_TIP_TABLE)
    tip_name_col = adapter._first_existing(tip_cols, ["HAREKETTIPI", "ACIKLAMA", "TANIM", "ADI", "ISIM"])
    tip_gc_col = adapter._first_existing(tip_cols, ["GIRISCIKIS", "GC", "YON", "DIRECTION"])
    tip_id_col = adapter._first_existing(tip_cols, ["ID"])
    tip_name_map: Dict[int, str] = {}
    tip_gc_map: Dict[int, str] = {}
    if tip_id_col and (tip_name_col or tip_gc_col):
        try:
            cur = adapter.cn.cursor()
            cur.execute(
                f"SELECT {tip_id_col}, {tip_name_col or 'NULL'}, {tip_gc_col or 'NULL'} FROM {base.HAREKET_TIP_TABLE} WITH (NOLOCK)"
            )
            for r in cur.fetchall():
                try:
                    tid = int(r[0])
                    tip_name_map[tid] = str(r[1] or "").strip()
                    tip_gc_map[tid] = str(r[2] or "").strip()
                except Exception:
                    pass
        except Exception:
            pass

    def sqlcol(col: Optional[str], default: str = "NULL") -> str:
        return f"H.{col}" if col else default

    where_dt, params_dt = _v70_date_where("H", h_date, start, end)
    try:
        cur = adapter.cn.cursor()
        sql = f"""
            SELECT TOP 5000
                {sqlcol(h_date)}, {sqlcol(h_type)}, {sqlcol(h_qty, '0')},
                {sqlcol(h_amount, '0')}, {sqlcol(h_loc)}, {sqlcol(h_doc)},
                {sqlcol(h_desc)}, {sqlcol(h_cari)}
            FROM {base.HAREKET_TABLE} H WITH (NOLOCK)
            WHERE H.{h_stok}=? {where_dt}
            ORDER BY H.{h_date} DESC
        """
        cur.execute(sql, [int(stock_id)] + params_dt)
        for r in cur.fetchall():
            dt, tid, qty_raw, amount_raw, loc_id, doc, desc, cari_id = r
            try: qty = float(qty_raw or 0)
            except Exception: qty = 0.0
            try: amount = float(amount_raw or 0)
            except Exception: amount = 0.0
            try: tid_i = int(tid) if tid is not None else -1
            except Exception: tid_i = -1

            type_name = tip_name_map.get(tid_i, f"Tip {tid_i}" if tid_i >= 0 else "Hareket")
            category = _v70_movement_category(adapter, tid_i, type_name, str(desc or ""))
            direction = adapter._gc_direction(tip_gc_map.get(tid_i), tid_i, qty)
            signed_qty = abs(qty) * direction

            try: lid = int(loc_id) if loc_id is not None else None
            except Exception: lid = None
            location = depo_map.get(lid) or sube_map.get(lid) or (str(loc_id) if loc_id is not None else "")
            try: cid = int(cari_id) if cari_id is not None else None
            except Exception: cid = None
            cari_name = cari_map.get(cid, "")
            unit_price = abs(amount) / abs(qty) if qty else 0.0

            out.append({
                "db": str(db_name).upper(),
                "date": dt,
                "category": category,
                "type": type_name,
                "location": location,
                "document": str(doc or ""),
                "qty": signed_qty,
                "unit_price": unit_price,
                "amount": abs(amount),
                "detail": cari_name or str(desc or ""),
            })
    except Exception as exc:
        try: base.debug_print(f"{str(db_name).upper()} V70 hareket sorgusu: {exc}")
        except Exception: pass

    return out


# =============================================================================
# SAYIM TABLOLARINI DİNAMİK KEŞFET VE ÜRÜN SAYIMLARINI EKLE
# =============================================================================
def _v70_table_names_like(adapter, pattern: str) -> List[str]:
    if not adapter.cn:
        return []
    try:
        cur = adapter.cn.cursor()
        cur.execute(
            "SELECT TABLE_SCHEMA, TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE' AND TABLE_NAME LIKE ? ORDER BY TABLE_NAME",
            (pattern,),
        )
        return [f"{r[0]}.{r[1]}" for r in cur.fetchall()]
    except Exception:
        return []


def _v70_pick(cols: List[str], names: List[str]) -> Optional[str]:
    upper = {str(c).upper(): str(c).upper() for c in cols}
    for name in names:
        if name.upper() in upper:
            return name.upper()
    return None


def _v70_load_sayim_movements(adapter, stock_id: int, db_name: str, start: Optional[date], end: Optional[date]) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    if not adapter.cn or not stock_id:
        return results

    tables = _v70_table_names_like(adapter, "%SAYIM%")
    if not tables:
        return results

    main_table = next((t for t in tables if t.split(".")[-1].upper() == "TBL_SAYIM_MAIN"), None)
    if not main_table:
        main_table = next((t for t in tables if "MAIN" in t.split(".")[-1].upper()), None)

    main_cols = adapter._table_cols(main_table) if main_table else []
    m_id = _v70_pick(main_cols, ["ID", "SAYIMID", "BELGEID"])
    m_date = _v70_pick(main_cols, ["BELGETARIHI", "TARIH", "SAYIMTARIHI", "CREATEDATE"])
    m_depo = _v70_pick(main_cols, ["DEPOID", "SUBEID", "MAGAZAID"])
    m_doc = _v70_pick(main_cols, ["BELGEKODU", "BELGENO", "SAYIMKODU", "FISNO"])
    m_desc = _v70_pick(main_cols, ["ACIKLAMA", "NOT", "NOTLAR", "DESCRIPTION"])

    depo_map = adapter._id_name_map(base.DEPO_TABLE, ["DEPOADI", "DEPO_ADI", "ACIKLAMA", "ADI", "ISIM", "TANIM"])
    sube_map = adapter._id_name_map(base.SUBE_TABLE, ["SUBEADI", "SUBE_ADI", "ACIKLAMA", "ADI", "ISIM", "TANIM"])

    # Önce detay adayı tabloları puanla.
    candidates = []
    for table in tables:
        if table == main_table:
            continue
        cols = adapter._table_cols(table)
        d_stok = _v70_pick(cols, ["STOKID", "STOKKARTID", "STOK_ID"])
        d_qty = _v70_pick(cols, [
            "SAYIMMIKTARI", "SAYILANMIKTAR", "SAYILAN_MIKTAR", "SAYILAN", "MIKTAR", "ADET", "QTY",
            "MEVCUTMIKTAR", "MEVCUT_MIKTAR"
        ])
        d_link = _v70_pick(cols, ["SAYIMID", "SAYIM_ID", "SAYIMMAINID", "SAYIM_MAIN_ID", "BELGEID", "MAINID"])
        d_diff = _v70_pick(cols, ["FARK", "FARKMIKTARI", "FARK_MIKTARI", "MIKTARFARKI", "MIKTAR_FARKI"])
        d_date = _v70_pick(cols, ["BELGETARIHI", "TARIH", "SAYIMTARIHI", "CREATEDATE"])
        d_depo = _v70_pick(cols, ["DEPOID", "SUBEID", "MAGAZAID"])
        d_doc = _v70_pick(cols, ["BELGEKODU", "BELGENO", "SAYIMKODU", "FISNO"])
        if d_stok and d_qty:
            score = 10 + (5 if d_link else 0) + (3 if "DETAY" in table.upper() else 0) + (2 if d_diff else 0)
            candidates.append((score, table, cols, d_stok, d_qty, d_link, d_diff, d_date, d_depo, d_doc))
    candidates.sort(key=lambda x: x[0], reverse=True)

    for _score, table, cols, d_stok, d_qty, d_link, d_diff, d_date, d_depo, d_doc in candidates:
        try:
            cur = adapter.cn.cursor()
            if main_table and m_id and d_link and m_date:
                where_dt, params_dt = _v70_date_where("M", m_date, start, end)
                sel_depo = f"M.{m_depo}" if m_depo else (f"D.{d_depo}" if d_depo else "NULL")
                sel_doc = f"M.{m_doc}" if m_doc else (f"D.{d_doc}" if d_doc else "NULL")
                sel_desc = f"M.{m_desc}" if m_desc else "NULL"
                sel_diff = f"D.{d_diff}" if d_diff else "NULL"
                sql = f"""
                    SELECT TOP 2000 M.{m_date}, {sel_doc}, {sel_depo}, D.{d_qty}, {sel_diff}, {sel_desc}
                    FROM {main_table} M WITH (NOLOCK)
                    INNER JOIN {table} D WITH (NOLOCK) ON D.{d_link}=M.{m_id}
                    WHERE D.{d_stok}=? {where_dt}
                    ORDER BY M.{m_date} DESC
                """
                cur.execute(sql, [int(stock_id)] + params_dt)
            elif d_date:
                where_dt, params_dt = _v70_date_where("D", d_date, start, end)
                sel_depo = f"D.{d_depo}" if d_depo else "NULL"
                sel_doc = f"D.{d_doc}" if d_doc else "NULL"
                sel_diff = f"D.{d_diff}" if d_diff else "NULL"
                sql = f"""
                    SELECT TOP 2000 D.{d_date}, {sel_doc}, {sel_depo}, D.{d_qty}, {sel_diff}, NULL
                    FROM {table} D WITH (NOLOCK)
                    WHERE D.{d_stok}=? {where_dt}
                    ORDER BY D.{d_date} DESC
                """
                cur.execute(sql, [int(stock_id)] + params_dt)
            else:
                continue

            rows = cur.fetchall()
            if not rows:
                continue

            for dt, doc, depo_id, qty_raw, diff_raw, desc in rows:
                try: qty = float(qty_raw or 0)
                except Exception: qty = 0.0
                try: diff = float(diff_raw) if diff_raw is not None else None
                except Exception: diff = None
                try: did = int(depo_id) if depo_id is not None else None
                except Exception: did = None
                location = depo_map.get(did) or sube_map.get(did) or (str(depo_id) if depo_id is not None else "")
                detail = str(desc or "Sayım kaydı")
                if diff is not None:
                    try:
                        detail += f" | Fark: {diff:g}"
                    except Exception:
                        pass
                results.append({
                    "db": str(db_name).upper(),
                    "date": dt,
                    "category": "Sayım",
                    "type": "Stok Sayımı",
                    "location": location,
                    "document": str(doc or ""),
                    "qty": qty,
                    "unit_price": 0.0,
                    "amount": 0.0,
                    "detail": detail,
                })

            # En güçlü ve veri döndüren detay tablosu yeterli; aynı sayımı başka detay tablosundan çoğaltma.
            if results:
                break
        except Exception:
            continue

    # Bazı sistemlerde sayım satırı doğrudan MAIN tablosunda olabilir.
    if not results and main_table:
        try:
            cols = main_cols
            s_stok = _v70_pick(cols, ["STOKID", "STOKKARTID", "STOK_ID"])
            s_qty = _v70_pick(cols, ["SAYIMMIKTARI", "SAYILANMIKTAR", "SAYILAN", "MIKTAR", "ADET"])
            if s_stok and s_qty and m_date:
                cur = adapter.cn.cursor()
                where_dt, params_dt = _v70_date_where("M", m_date, start, end)
                sel_depo = f"M.{m_depo}" if m_depo else "NULL"
                sel_doc = f"M.{m_doc}" if m_doc else "NULL"
                sel_desc = f"M.{m_desc}" if m_desc else "NULL"
                cur.execute(f"""
                    SELECT TOP 2000 M.{m_date}, {sel_doc}, {sel_depo}, M.{s_qty}, {sel_desc}
                    FROM {main_table} M WITH (NOLOCK)
                    WHERE M.{s_stok}=? {where_dt}
                    ORDER BY M.{m_date} DESC
                """, [int(stock_id)] + params_dt)
                for dt, doc, depo_id, qty_raw, desc in cur.fetchall():
                    try: qty = float(qty_raw or 0)
                    except Exception: qty = 0.0
                    try: did = int(depo_id) if depo_id is not None else None
                    except Exception: did = None
                    location = depo_map.get(did) or sube_map.get(did) or str(depo_id or "")
                    results.append({
                        "db": str(db_name).upper(), "date": dt, "category": "Sayım", "type": "Stok Sayımı",
                        "location": location, "document": str(doc or ""), "qty": qty,
                        "unit_price": 0.0, "amount": 0.0, "detail": str(desc or "Sayım kaydı"),
                    })
        except Exception:
            pass

    return results


def _v70_dedupe_movements(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    seen = set()
    for r in rows:
        dt = r.get("date")
        try:
            dt_key = dt.strftime("%Y-%m-%d %H:%M:%S") if hasattr(dt, "strftime") else str(dt or "")
        except Exception:
            dt_key = str(dt or "")
        key = (
            str(r.get("db") or ""), str(r.get("category") or ""), dt_key,
            str(r.get("document") or ""), str(r.get("location") or ""),
            round(float(r.get("qty") or 0), 6),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    try:
        out.sort(key=lambda x: x.get("date") or datetime.datetime.min, reverse=True)
    except Exception:
        pass
    return out


# =============================================================================
# V70 DASHBOARD WORKER: HALK + LİMON + TARİH ARALIĞI + SAYIM
# =============================================================================
def _v70_dashboard_worker(self, barcode: str, token: int):
    dashboards: List[Dict[str, Any]] = []
    errors: List[str] = []
    stock_code = str(getattr(self, "_v69_dashboard_stock_code", "") or "").strip()
    start = getattr(self, "_v70_start_date", None)
    end = getattr(self, "_v70_end_date", None)

    for db_name, cfg in self.db_configs.items():
        ad = base.DBAdapter(db_name, cfg)
        ok, msg = ad.connect()
        if not ok:
            errors.append(f"{str(db_name).upper()}: {msg}")
            continue
        try:
            stock_id = v69._v69_find_stock_id(ad, barcode, stock_code)
            if not stock_id:
                errors.append(f"{str(db_name).upper()}: ürün bulunamadı")
                continue

            dash = ad.get_stock_dashboard(int(stock_id), db_name)
            moves = _v70_load_stock_movements(ad, int(stock_id), db_name, start, end)
            sayim_moves = _v70_load_sayim_movements(ad, int(stock_id), db_name, start, end)
            dash["movements"] = _v70_dedupe_movements(moves + sayim_moves)
            dashboards.append(dash)
        except Exception as exc:
            errors.append(f"{str(db_name).upper()}: {exc}")
        finally:
            try:
                if ad.cn:
                    ad.cn.close()
            except Exception:
                pass

    try:
        self.after(0, lambda: self._render_dashboard(barcode, token, dashboards, errors))
    except Exception:
        pass


base.App._dashboard_worker = _v70_dashboard_worker


# V69 render sonrası dönem bilgisini koru.
_ORIG_RENDER_V70 = base.App._render_dashboard


def _v70_render_dashboard(self, barcode: str, token: int, dashboards: List[Dict[str, Any]], errors: List[str]):
    _ORIG_RENDER_V70(self, barcode, token, dashboards, errors)
    if token != getattr(self, "_dashboard_token", token):
        return
    try:
        start = getattr(self, "_v70_start_date", None)
        end = getattr(self, "_v70_end_date", None)
        self.lbl_v70_period.configure(text=_v70_period_text(start, end))
    except Exception:
        pass


base.App._render_dashboard = _v70_render_dashboard


if __name__ == "__main__":
    login_app = base.LoginWindow()
    login_app.mainloop()
