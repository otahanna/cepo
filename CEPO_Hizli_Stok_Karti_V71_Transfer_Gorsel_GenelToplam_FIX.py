# -*- coding: utf-8 -*-
"""
CEPO Hızlı Stok Kartı V71

V70 üzerine eklenen düzeltmeler:
- Transfer hareket tipi 20 ve 51 kesin olarak Transfer sınıfına alınır.
- TBL_STOK_HAREKET'te görünmeyen transferler ayrıca TBL_DEPO_FIS_MAIN / DETAY'dan okunur.
- Tarih aralığı transfer sorgularına da uygulanır.
- Google Görseller motoru güçlendirildi: özgün URL, encrypted-tbn küçük görsel ve sayfa içi base64 önizleme denenir.
- Şube / Depo bakiye tablosunun en altına GENEL TOPLAM satırı eklenir.
- Genel toplam satırı toplam bakiye ve toplam stok tutarını gösterir.
- V70'in Türkçe tarih seçimi, Sayım hareketleri, HALK + LİMON stokları korunur.

KULLANIM:
CEPO_Hizli_Stok_Karti_V65_Referans_Profesyonel.py ile aynı klasöre koyup V71'i çalıştırın.
V70 ve alt yardımcı sürümler yoksa internetten otomatik indirilmeye çalışılır.
"""

from __future__ import annotations

import os
import sys
import io
import re
import html
import base64
import threading
import importlib.util
import urllib.parse
import urllib.request
import datetime
from typing import Any, Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
V70_FILE = "CEPO_Hizli_Stok_Karti_V70_Tarih_Araligi_Sayim_FIX.py"
V70_PATH = os.path.join(HERE, V70_FILE)
V70_URL = "https://raw.githubusercontent.com/otahanna/cepo/main/CEPO_Hizli_Stok_Karti_V70_Tarih_Araligi_Sayim_FIX.py"


def _v71_download(url: str, path: str) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 CEPO-Hizli-Stok-V71"})
    with urllib.request.urlopen(req, timeout=35) as resp:
        data = resp.read()
    with open(path, "wb") as f:
        f.write(data)


if not os.path.isfile(V70_PATH):
    try:
        _v71_download(V70_URL, V70_PATH)
    except Exception as exc:
        raise SystemExit("V70 yardımcı dosyası indirilemedi:\n" + str(exc))

spec = importlib.util.spec_from_file_location("cepo_hizli_stok_v70_base", V70_PATH)
if spec is None or spec.loader is None:
    raise SystemExit("V70 modülü yüklenemedi.")
v70 = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = v70
spec.loader.exec_module(v70)

v69 = v70.v69
v68 = v70.v68
v67 = v70.v67
base = v70.base
base.APP_TITLE = "CEPO Hızlı Stok Kartı V71"

try:
    from PIL import Image
    PIL_OK = True
except Exception:
    Image = None
    PIL_OK = False


# =============================================================================
# 1) TRANSFER SINIFLANDIRMASI: 20 + 51
# =============================================================================
_ORIG_MOVEMENT_CATEGORY_V71 = base.DBAdapter._movement_category


def _v71_movement_category(type_id: Any, type_name: str = "", description: str = "") -> str:
    try:
        tid = int(type_id)
    except Exception:
        tid = -1
    if tid in (20, 51):
        return "Transfer"

    txt = f"{type_name or ''} {description or ''}".upper()
    txt = txt.translate(str.maketrans({"İ":"I", "Ş":"S", "Ğ":"G", "Ü":"U", "Ö":"O", "Ç":"C"}))
    if any(x in txt for x in ("TRANSFER", "SEVK", "DEPO FIS", "DEPOFIS", "DEPO AKTAR")):
        return "Transfer"

    return _ORIG_MOVEMENT_CATEGORY_V71(type_id, type_name, description)


base.DBAdapter._movement_category = staticmethod(_v71_movement_category)


# =============================================================================
# 2) DEPO FİŞLERİNDEN TRANSFERLERİ AYRICA OKU
# =============================================================================
def _v71_load_transfer_movements(
    adapter,
    stock_id: int,
    db_name: str,
    start,
    end,
) -> List[Dict[str, Any]]:
    rows_out: List[Dict[str, Any]] = []
    if not getattr(adapter, "cn", None) or not stock_id:
        return rows_out

    try:
        main_table = base.DEPO_FIS_MAIN_TABLE
        detail_table = base.DEPO_FIS_DETAY_TABLE
        mcols = adapter._table_cols(main_table)
        dcols = adapter._table_cols(detail_table)
        if not mcols or not dcols:
            return rows_out

        m_id = adapter._first_existing(mcols, ["ID", "BELGEID", "FISID"])
        m_date = adapter._first_existing(mcols, ["BELGETARIHI", "TARIH", "ISLEMTARIHI", "CREATEDATE"])
        m_out = adapter._first_existing(mcols, ["CIKISDEPOID", "CIKISSUBEID", "CIKIS_DEPO_ID"])
        m_in = adapter._first_existing(mcols, ["GIRISDEPOID", "GIRISSUBEID", "GIRIS_DEPO_ID"])
        m_doc = adapter._first_existing(mcols, ["BELGEKODU", "BELGENO", "FISNO", "EVRAKNO"])
        m_desc = adapter._first_existing(mcols, ["ACIKLAMA", "NOT", "NOTLAR", "DESCRIPTION"])
        m_type = adapter._first_existing(mcols, ["HAREKETTIPID", "TIPID", "HAREKETTIPI"])

        d_link = adapter._first_existing(dcols, ["BELGEID", "FISID", "MAINID", "DEPOFISID"])
        d_stok = adapter._first_existing(dcols, ["STOKID", "STOKKARTID", "STOK_ID"])
        d_qty = adapter._first_existing(dcols, ["MIKTAR", "ADET", "QTY", "MIKTAR1"])

        if not all([m_id, m_date, d_link, d_stok, d_qty]):
            return rows_out

        depo_map = adapter._id_name_map(
            base.DEPO_TABLE,
            ["DEPOADI", "DEPO_ADI", "ACIKLAMA", "ADI", "ISIM", "TANIM"],
        )
        sube_map = adapter._id_name_map(
            base.SUBE_TABLE,
            ["SUBEADI", "SUBE_ADI", "ACIKLAMA", "ADI", "ISIM", "TANIM"],
        )

        def loc_name(v: Any) -> str:
            try:
                key = int(v) if v is not None else None
            except Exception:
                key = None
            return depo_map.get(key) or sube_map.get(key) or (str(v) if v is not None else "")

        where_dt, params_dt = v70._v70_date_where("F", m_date, start, end)
        doc_expr = f"F.{m_doc}" if m_doc else "NULL"
        desc_expr = f"F.{m_desc}" if m_desc else "NULL"
        out_expr = f"F.{m_out}" if m_out else "NULL"
        in_expr = f"F.{m_in}" if m_in else "NULL"
        type_expr = f"F.{m_type}" if m_type else "NULL"

        cur = adapter.cn.cursor()
        cur.execute(
            f"""
            SELECT TOP 5000
                F.{m_date}, {doc_expr}, {out_expr}, {in_expr}, D.{d_qty}, {desc_expr}, {type_expr}
            FROM {main_table} F WITH (NOLOCK)
            INNER JOIN {detail_table} D WITH (NOLOCK) ON D.{d_link}=F.{m_id}
            WHERE D.{d_stok}=? {where_dt}
            ORDER BY F.{m_date} DESC
            """,
            [int(stock_id)] + params_dt,
        )

        for dt, doc, out_id, in_id, qty_raw, desc, type_id in cur.fetchall():
            try:
                qty = abs(float(qty_raw or 0))
            except Exception:
                qty = 0.0
            out_name = loc_name(out_id)
            in_name = loc_name(in_id)
            if out_name and in_name:
                location = f"{out_name} → {in_name}"
            else:
                location = out_name or in_name
            try:
                tid = int(type_id) if type_id is not None else -1
            except Exception:
                tid = -1
            type_text = "Depo Transferi" if tid < 0 else f"Depo Transferi (Tip {tid})"
            rows_out.append({
                "db": str(db_name).upper(),
                "date": dt,
                "category": "Transfer",
                "type": type_text,
                "location": location,
                "document": str(doc or ""),
                "qty": qty,
                "unit_price": 0.0,
                "amount": 0.0,
                "detail": str(desc or "Depo transferi"),
            })
    except Exception as exc:
        try:
            base.debug_print(f"{str(db_name).upper()} V71 depo transfer sorgusu: {exc}")
        except Exception:
            pass
    return rows_out


def _v71_dedupe_movements(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # Önce V70'in genel tekrar temizliğini uygula.
    rows = v70._v70_dedupe_movements(rows)
    out: List[Dict[str, Any]] = []
    transfer_index: Dict[Tuple[str, str, str, float], int] = {}

    for r in rows:
        if str(r.get("category") or "") != "Transfer":
            out.append(r)
            continue

        dt = r.get("date")
        try:
            dt_key = dt.strftime("%Y-%m-%d") if hasattr(dt, "strftime") else str(dt or "")[:10]
        except Exception:
            dt_key = str(dt or "")[:10]
        try:
            qty_key = round(abs(float(r.get("qty") or 0)), 5)
        except Exception:
            qty_key = 0.0
        key = (
            str(r.get("db") or ""),
            str(r.get("document") or ""),
            dt_key,
            qty_key,
        )

        if key not in transfer_index:
            transfer_index[key] = len(out)
            out.append(r)
            continue

        # Aynı transferin iki kaydı varsa çıkış→giriş bilgisi daha açıklayıcı olanı koru.
        old_i = transfer_index[key]
        old = out[old_i]
        old_loc = str(old.get("location") or "")
        new_loc = str(r.get("location") or "")
        if "→" in new_loc and "→" not in old_loc:
            out[old_i] = r

    try:
        out.sort(key=lambda x: x.get("date") or datetime.datetime.min, reverse=True)
    except Exception:
        pass
    return out


# =============================================================================
# 3) V71 WORKER: HAREKET + SAYIM + DEPO TRANSFERİ
# =============================================================================
def _v71_dashboard_worker(self, barcode: str, token: int):
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
            stock_moves = v70._v70_load_stock_movements(ad, int(stock_id), db_name, start, end)
            sayim_moves = v70._v70_load_sayim_movements(ad, int(stock_id), db_name, start, end)
            transfer_moves = _v71_load_transfer_movements(ad, int(stock_id), db_name, start, end)
            dash["movements"] = _v71_dedupe_movements(stock_moves + sayim_moves + transfer_moves)
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


base.App._dashboard_worker = _v71_dashboard_worker


# =============================================================================
# 4) ŞUBE BAKİYELERİNİN ALTINA GENEL TOPLAM SATIRI
# =============================================================================
_ORIG_RENDER_V71 = base.App._render_dashboard


def _v71_render_dashboard(self, barcode: str, token: int, dashboards: List[Dict[str, Any]], errors: List[str]):
    _ORIG_RENDER_V71(self, barcode, token, dashboards, errors)
    if token != getattr(self, "_dashboard_token", token):
        return

    total_balance = 0.0
    total_amount = 0.0
    for dash in dashboards:
        sm = dash.get("summary", {}) or {}
        try:
            balance = float(sm.get("balance") or 0)
        except Exception:
            balance = 0.0
        try:
            amount = float(sm.get("stock_amount") or 0)
        except Exception:
            amount = 0.0
        if not amount:
            try:
                amount = balance * float(sm.get("last_cost") or 0)
            except Exception:
                amount = 0.0
        total_balance += balance
        total_amount += amount

    try:
        # Önceki render tekrar çağrılmışsa eski genel toplamı kaldır.
        for iid in self.branch_tree.get_children():
            vals = self.branch_tree.item(iid, "values")
            if vals and len(vals) > 1 and str(vals[1]).strip().upper() == "GENEL TOPLAM":
                self.branch_tree.delete(iid)

        try:
            self.branch_tree.tag_configure(
                "v71_general_total",
                background="#E4F4D2",
                foreground="#162119",
                font=("Segoe UI Semibold", 10),
            )
        except Exception:
            pass

        self.branch_tree.insert(
            "",
            "end",
            values=(
                "",
                "GENEL TOPLAM",
                self._fmt_number(total_balance, 3),
                "",
                self._fmt_money(total_amount),
                "",
            ),
            tags=("v71_general_total",),
        )
    except Exception as exc:
        try:
            base.debug_print(f"V71 genel toplam satırı eklenemedi: {exc}")
        except Exception:
            pass


base.App._render_dashboard = _v71_render_dashboard


# =============================================================================
# 5) GOOGLE GÖRSELLER - BASE64 + THUMBNAIL + ÖZGÜN URL
# =============================================================================
def _v71_google_headers(image: bool = False) -> Dict[str, str]:
    h = dict(v69._v69_google_headers(image))
    h["Cache-Control"] = "no-cache"
    h["Pragma"] = "no-cache"
    return h


def _v71_fetch_google_page(query: str) -> List[str]:
    q = urllib.parse.quote_plus(str(query or "").strip())
    urls = [
        f"https://www.google.com/search?tbm=isch&gbv=1&hl=tr&gl=tr&safe=off&filter=0&q={q}",
        f"https://images.google.com/images?tbm=isch&hl=tr&gl=tr&safe=off&q={q}",
        f"https://www.google.com/search?udm=2&hl=tr&gl=tr&safe=off&q={q}",
    ]
    pages: List[str] = []
    for url in urls:
        try:
            req = urllib.request.Request(url, headers=_v71_google_headers(False))
            with urllib.request.urlopen(req, timeout=25) as resp:
                raw = resp.read(12 * 1024 * 1024)
                ctype = str(resp.headers.get("Content-Type") or "")
            enc = "utf-8"
            m = re.search(r"charset=([\w\-]+)", ctype, re.I)
            if m:
                enc = m.group(1)
            pages.append(raw.decode(enc, errors="replace"))
        except Exception:
            continue
    return pages


def _v71_image_from_bytes(raw: bytes):
    if not PIL_OK or not raw or len(raw) < 1200:
        return None
    try:
        img = Image.open(io.BytesIO(raw)).convert("RGBA")
        if img.width < 60 or img.height < 60:
            return None
        return img
    except Exception:
        return None


def _v71_inline_images(page: str) -> List[bytes]:
    out: List[bytes] = []
    for _fmt, payload in re.findall(
        r"data:image/(jpeg|jpg|png|webp);base64,([A-Za-z0-9+/=]{1500,})",
        page or "",
        flags=re.I,
    ):
        try:
            raw = base64.b64decode(payload)
            if len(raw) > 1500:
                out.append(raw)
        except Exception:
            pass
        if len(out) >= 20:
            break
    return out


def _v71_extract_google_urls(page: str) -> List[str]:
    normalized = html.unescape(page or "")
    normalized = normalized.replace("\\u003d", "=").replace("\\u0026", "&").replace("\\/", "/")
    urls: List[str] = []

    # Google sonuç küçük görselleri. Bunlar kullanıcı tarafında genellikle en güvenilir indirilebilir sonuçlardır.
    thumb_patterns = [
        r"https://encrypted-tbn\d+\.gstatic\.com/images\?[^\"'<>\\\s]+",
        r"https://encrypted-tbn\d+\.gstatic\.com/images\?q=tbn:[^\"'<>\\\s]+",
        r"https://www\.google\.com/images\?q=tbn:[^\"'<>\\\s]+",
    ]
    for pat in thumb_patterns:
        for u in re.findall(pat, normalized, flags=re.I):
            u = v69._v69_decode_url(u)
            if u and u not in urls:
                urls.append(u)

    # V69 özgün URL motorunu da kullan.
    for pat in (
        r'(?:imgurl|mediaurl)=([^&"\'<>\s]+)',
        r'"ou"\s*:\s*"(https?://[^"\\]+)',
        r'"originalImageUrl"\s*:\s*"(https?://[^"\\]+)',
        r'"imageUrl"\s*:\s*"(https?://[^"\\]+)',
    ):
        for found in re.findall(pat, normalized, flags=re.I):
            u = v69._v69_decode_url(found)
            if u and u.startswith(("http://", "https://")) and u not in urls:
                urls.append(u)

    # HTML img src/data-src alanları.
    for found in re.findall(r'''<img[^>]+(?:src|data-src)=["'](https?://[^"']+)["']''', normalized, flags=re.I):
        u = v69._v69_decode_url(found)
        low = u.lower()
        if any(x in low for x in ("logo", "favicon", "branding")):
            continue
        if u not in urls:
            urls.append(u)

    return urls[:80]


def _v71_cache_path(barcode: str) -> str:
    safe = re.sub(r"[^0-9A-Za-z_.-]+", "_", str(barcode or "urun"))
    return os.path.join(v67._v67_cache_dir(), "google_v71_" + safe + ".png")


def _v71_download_image_url(url: str) -> Optional[bytes]:
    headers = _v71_google_headers(True)
    headers["Referer"] = "https://www.google.com/"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=25) as resp:
            return resp.read(16 * 1024 * 1024)
    except Exception:
        return None


def _v71_download_google_image(product_name: str, barcode: str):
    if not PIL_OK:
        return None, ""

    cache = _v71_cache_path(barcode)
    if os.path.isfile(cache):
        try:
            return Image.open(cache).convert("RGBA"), "Google Görseller"
        except Exception:
            pass

    queries: List[str] = []
    for q in (
        " ".join(x for x in (str(product_name or "").strip(), str(barcode or "").strip()) if x),
        str(barcode or "").strip(),
        str(product_name or "").strip(),
    ):
        if q and q not in queries:
            queries.append(q)

    for q in queries:
        pages = _v71_fetch_google_page(q)

        # 1) Google sayfasının içine gömülü ilk gerçek önizleme resmi.
        for page in pages:
            for raw in _v71_inline_images(page):
                img = _v71_image_from_bytes(raw)
                if img is None:
                    continue
                try:
                    img = v67._v67_remove_background(img) or img
                except Exception:
                    pass
                try:
                    img.save(cache, "PNG", optimize=True)
                except Exception:
                    pass
                return img, "Google Görseller"

        # 2) Google thumbnail / özgün kaynak URL'leri.
        urls: List[str] = []
        for page in pages:
            for u in _v71_extract_google_urls(page):
                if u not in urls:
                    urls.append(u)
        try:
            for u in v69._v69_google_candidates(q):
                if u not in urls:
                    urls.append(u)
        except Exception:
            pass

        for u in urls[:80]:
            raw = _v71_download_image_url(u)
            img = _v71_image_from_bytes(raw or b"")
            if img is None:
                continue
            try:
                img = v67._v67_remove_background(img) or img
            except Exception:
                pass
            try:
                img.save(cache, "PNG", optimize=True)
            except Exception:
                pass
            return img, "Google Görseller"

    # Son yedek: önceki kaynak motorları.
    try:
        return v67._v67_download_product_image(barcode)
    except Exception:
        return None, ""


def _v71_start_product_image(self, barcode: str):
    digits = re.sub(r"\D+", "", str(barcode or ""))
    if not digits:
        return
    try:
        product_name = (self.ent_stokadi.get() or "").strip()
    except Exception:
        product_name = ""

    self._v67_image_token = int(getattr(self, "_v67_image_token", 0)) + 1
    token = self._v67_image_token
    try:
        v67._v67_set_image_status(self, "GOOGLE GÖRSELLER'DE ARANIYOR...\n" + (product_name or digits))
    except Exception:
        pass

    def worker():
        image, source = _v71_download_google_image(product_name, digits)
        try:
            self.after(0, lambda: v67._v67_apply_product_image(self, token, image, source))
        except Exception:
            pass

    threading.Thread(target=worker, daemon=True).start()


def _v71_load_product_dashboard(self, barcode: Optional[str] = None):
    b = (barcode or (self.ent_barkod.get() if hasattr(self, "ent_barkod") else "") or "").strip()
    if not b:
        self._clear_dashboard()
        return
    try:
        self._v69_dashboard_stock_code = (self.ent_stokkod.get() or "").strip()
    except Exception:
        self._v69_dashboard_stock_code = ""

    # Dashboard worker V71'dir. Görseli de yalnız V71 motoru başlatır.
    result = v67._ORIG_LOAD_PRODUCT_DASHBOARD(self, b)
    _v71_start_product_image(self, b)
    return result


base.App.load_product_dashboard = _v71_load_product_dashboard


if __name__ == "__main__":
    login_app = base.LoginWindow()
    login_app.mainloop()
