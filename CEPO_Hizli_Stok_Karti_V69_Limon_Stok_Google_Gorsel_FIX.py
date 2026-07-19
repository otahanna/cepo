# -*- coding: utf-8 -*-
"""
CEPO Hızlı Stok Kartı V69

Düzeltmeler:
- HALK seçili olsa bile LİMON stokları da Şube Bilgileri tablosunda gösterilir.
- LİMON tarafında barkod farklı olsa bile aynı STOKKODU ile ürün bulunup stokları getirilir.
- Bakiye = TBL_STOK_HAREKET.DEPOID bazında SUM(MIKTAR).
- Alt tablo: DB | Şube/Depo | Bakiye | Son Maliyet | Tutar | Son Hareket.
- Google Görseller araması güçlendirildi. Özgün görsel URL'si bulunamazsa ilk Google sonuç küçük görseli kullanılır.
- Görsel arama: Ürün Adı + Barkod, ardından Barkod, ardından Ürün Adı.
- Görsel arka planı V67 motoruyla temizlenir ve barkod bazında önbelleğe alınır.

KULLANIM:
CEPO_Hizli_Stok_Karti_V65_Referans_Profesyonel.py ile aynı klasöre koyup V69'u çalıştırın.
V68/V67 yoksa internetten otomatik indirilmeye çalışılır.
"""

from __future__ import annotations

import os
import sys
import io
import re
import html
import json
import threading
import importlib.util
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
V68_FILE = "CEPO_Hizli_Stok_Karti_V68_Google_Gorsel.py"
V68_PATH = os.path.join(HERE, V68_FILE)
V68_URL = "https://raw.githubusercontent.com/otahanna/cepo/main/CEPO_Hizli_Stok_Karti_V68_Google_Gorsel.py"


def _download_helper(url: str, path: str) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 CEPO-Hizli-Stok-V69"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
    with open(path, "wb") as f:
        f.write(data)


if not os.path.isfile(V68_PATH):
    try:
        _download_helper(V68_URL, V68_PATH)
    except Exception as exc:
        raise SystemExit("V68 yardımcı dosyası indirilemedi:\n" + str(exc))

spec = importlib.util.spec_from_file_location("cepo_hizli_stok_v68_base", V68_PATH)
if spec is None or spec.loader is None:
    raise SystemExit("V68 modülü yüklenemedi.")
v68 = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = v68
spec.loader.exec_module(v68)

v67 = v68.v67
base = v68.base
base.APP_TITLE = "CEPO Hızlı Stok Kartı V69"

try:
    from PIL import Image
    PIL_OK = True
except Exception:
    Image = None
    PIL_OK = False


# =============================================================================
# 1) LİMON ÜRÜNÜNÜ BARKOD + STOK KODU İLE BUL
# =============================================================================
def _v69_find_stock_id(adapter, barcode: str, stock_code: str = "") -> Optional[int]:
    try:
        found = adapter.get_stock_details_by_barcode(barcode)
        if found and found.get("real_id"):
            return int(found["real_id"])
    except Exception:
        pass

    code = str(stock_code or "").strip()
    if not code or not getattr(adapter, "cn", None):
        return None

    try:
        cols = adapter._table_cols(base.MAIN_TABLE)
        code_col = adapter._first_existing(cols, ["STOKKODU", "STOK_KODU", "KOD"])
        if not code_col:
            return None
        cur = adapter.cn.cursor()
        cur.execute(
            f"SELECT TOP 1 ID FROM {base.MAIN_TABLE} WITH (NOLOCK) WHERE {code_col}=?",
            (code,),
        )
        row = cur.fetchone()
        if row and row[0] is not None:
            return int(row[0])
    except Exception:
        pass
    return None


def _v69_dashboard_worker(self, barcode: str, token: int):
    dashboards: List[Dict[str, Any]] = []
    errors: List[str] = []
    stock_code = str(getattr(self, "_v69_dashboard_stock_code", "") or "").strip()

    for db_name, cfg in self.db_configs.items():
        ad = base.DBAdapter(db_name, cfg)
        ok, msg = ad.connect()
        if not ok:
            errors.append(f"{str(db_name).upper()}: {msg}")
            continue
        try:
            stock_id = _v69_find_stock_id(ad, barcode, stock_code)
            if stock_id:
                dashboards.append(ad.get_stock_dashboard(int(stock_id), db_name))
            else:
                errors.append(f"{str(db_name).upper()}: ürün bulunamadı")
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


base.App._dashboard_worker = _v69_dashboard_worker


# =============================================================================
# 2) HALK + LİMON BİRLİKTE GÖSTER
# V67 seçili DB'ye filtreliyordu. V69 tüm bulunan DB'leri gösterir.
# =============================================================================
def _v69_render_dashboard(self, barcode: str, token: int, dashboards: List[Dict[str, Any]], errors: List[str]):
    # Hareketler ve alt istatistikler V65 motoruyla dolsun.
    v67._ORIG_RENDER_DASHBOARD(self, barcode, token, dashboards, errors)
    if token != getattr(self, "_dashboard_token", token):
        return

    try:
        for iid in self.branch_tree.get_children():
            self.branch_tree.delete(iid)
    except Exception:
        pass

    total_balance = 0.0
    total_amount = 0.0
    last_cost = 0.0
    last_purchase = None
    last_sale = None
    branch_count = 0
    db_names: List[str] = []

    for dash in dashboards:
        dbn = str(dash.get("db") or "").upper()
        if dbn and dbn not in db_names:
            db_names.append(dbn)

        sm = dash.get("summary", {}) or {}
        balance = float(sm.get("balance") or 0)
        cost = float(sm.get("last_cost") or 0)
        amount = float(sm.get("stock_amount") or (balance * cost))
        total_balance += balance
        total_amount += amount

        lp = sm.get("last_purchase")
        ls = sm.get("last_sale")
        if lp and (last_purchase is None or lp > last_purchase):
            last_purchase = lp
            last_cost = cost
        elif not last_purchase and cost:
            last_cost = cost
        if ls and (last_sale is None or ls > last_sale):
            last_sale = ls

        for br in dash.get("branches", []) or []:
            branch_count += 1
            bal = float(br.get("balance") or 0)
            br_cost = float(br.get("last_cost") or cost or 0)
            br_amount = float(br.get("amount") or (bal * br_cost))
            try:
                self.branch_tree.insert(
                    "",
                    "end",
                    values=(
                        br.get("db", dbn),
                        br.get("location", ""),
                        self._fmt_number(bal, 3),
                        self._fmt_money(br_cost),
                        self._fmt_money(br_amount),
                        self._fmt_date(br.get("last_date"), True),
                    ),
                )
            except Exception:
                pass

    try:
        self.summary_labels["balance"].configure(text=self._fmt_number(total_balance, 3))
    except Exception:
        pass
    try:
        self.summary_labels["last_cost"].configure(text=self._fmt_money(last_cost) if last_cost else "—")
    except Exception:
        pass
    try:
        if "amount" in self.summary_labels:
            self.summary_labels["amount"].configure(text=self._fmt_money(total_amount))
    except Exception:
        pass
    try:
        if last_purchase is not None:
            self.summary_labels["last_purchase"].configure(text=self._fmt_date(last_purchase))
        if last_sale is not None:
            self.summary_labels["last_sale"].configure(text=self._fmt_date(last_sale))
    except Exception:
        pass

    try:
        sale_price = float(str(self.ent_fiyat.get() or "0").replace(",", "."))
    except Exception:
        sale_price = 0.0
    profit_value = sale_price - last_cost
    margin = (profit_value / sale_price * 100.0) if sale_price else 0.0
    try:
        self.lbl_profit_amount.configure(
            text=f"Kâr: {self._fmt_money(profit_value)}",
            text_color=base.CEPO_GREEN_DARK if profit_value >= 0 else "#B42318",
        )
        self.lbl_profit_margin.configure(
            text=f"Marj: %{self._fmt_number(margin, 1)}",
            text_color=base.CEPO_GREEN_DARK if margin >= 0 else "#B42318",
        )
    except Exception:
        pass

    try:
        db_text = " + ".join(db_names) if db_names else "Kayıt bulunamadı"
        extra = f" | Hata: {'; '.join(errors)}" if errors else ""
        self.lbl_dashboard_info.configure(
            text=f"{barcode} • {db_text} • {branch_count} şube/depo • HALK + LİMON{extra}"
        )
    except Exception:
        pass


base.App._render_dashboard = _v69_render_dashboard


# =============================================================================
# 3) GOOGLE GÖRSELLER - YENİ HTML/JSON + THUMBNAIL FALLBACK
# =============================================================================
def _v69_google_headers(image: bool = False) -> Dict[str, str]:
    h = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
        "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.7,en;q=0.6",
        "Connection": "close",
        # Google onay sayfasına düşme ihtimalini azaltır.
        "Cookie": "CONSENT=YES+cb.20240101-17-p0.tr+FX+111; SOCS=CAESHAgBEhJnd3Nfd2ViX2ltYWdlc19zZWFyY2g",
    }
    if image:
        h["Accept"] = "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
    else:
        h["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
    return h


def _v69_fetch_text(url: str, timeout: int = 22) -> str:
    req = urllib.request.Request(url, headers=_v69_google_headers(False))
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read(10 * 1024 * 1024)
        ctype = str(resp.headers.get("Content-Type") or "")
    enc = "utf-8"
    m = re.search(r"charset=([\w\-]+)", ctype, re.I)
    if m:
        enc = m.group(1)
    try:
        return raw.decode(enc, errors="replace")
    except Exception:
        return raw.decode("utf-8", errors="replace")


def _v69_decode_url(value: str) -> str:
    u = html.unescape(str(value or ""))
    u = u.replace("\\u003d", "=").replace("\\u0026", "&").replace("\\u003f", "?")
    u = u.replace("\\/", "/").replace("\\x3d", "=").replace("\\x26", "&")
    u = u.strip(" \\t\\r\\n\\\"'[](),")
    try:
        if "%2F" in u or "%3A" in u:
            u = urllib.parse.unquote(u)
    except Exception:
        pass
    return u.strip()


def _v69_is_original_candidate(url: str) -> bool:
    low = str(url or "").lower()
    if not low.startswith(("http://", "https://")):
        return False
    bad = (
        "google.com/images/branding", "gstatic.com/images/branding", "googleapis.com",
        "youtube.com", "ytimg.com", "favicon", "sprite", "logo", "icon"
    )
    if any(x in low for x in bad):
        return False
    # Google thumbnail ayrı fallback listesine gider.
    if "encrypted-tbn" in low or "gstatic.com/images?q=tbn" in low:
        return False
    return True


def _v69_google_candidates(query: str) -> List[str]:
    q = str(query or "").strip()
    if not q:
        return []

    pages = []
    for url in (
        "https://www.google.com/search?tbm=isch&hl=tr&gl=tr&safe=off&filter=0&q=" + urllib.parse.quote_plus(q),
        "https://www.google.com/search?udm=2&hl=tr&gl=tr&safe=off&q=" + urllib.parse.quote_plus(q),
    ):
        try:
            pages.append(_v69_fetch_text(url))
        except Exception:
            pass

    originals: List[str] = []
    thumbnails: List[str] = []

    for raw_page in pages:
        page = html.unescape(raw_page or "")
        normalized = (
            page.replace("\\u003d", "=")
                .replace("\\u0026", "&")
                .replace("\\/", "/")
        )

        # En güvenilir: imgurl parametreleri.
        for found in re.findall(r"(?:imgurl|mediaurl)=([^&\"'<>\\s]+)", normalized, flags=re.I):
            u = _v69_decode_url(found)
            if _v69_is_original_candidate(u) and u not in originals:
                originals.append(u)

        # Eski/yeni Google JSON alanları.
        for pat in (
            r'"ou"\s*:\s*"(https?://[^"\\]+)',
            r'"originalImageUrl"\s*:\s*"(https?://[^"\\]+)',
            r'"imageUrl"\s*:\s*"(https?://[^"\\]+)',
        ):
            for found in re.findall(pat, normalized, flags=re.I):
                u = _v69_decode_url(found)
                if _v69_is_original_candidate(u) and u not in originals:
                    originals.append(u)

        # Sayfadaki tüm URL'leri tarayıp gerçek kaynakları yakala.
        for found in re.findall(r"https?://[^\"'<>\\s]+", normalized, flags=re.I):
            u = _v69_decode_url(found)
            low = u.lower()
            if ("encrypted-tbn" in low or "gstatic.com/images?q=tbn" in low):
                if u not in thumbnails:
                    thumbnails.append(u)
                continue
            if _v69_is_original_candidate(u):
                # Görsel dosyası ya da yaygın ürün CDN'i ise önceliklendir.
                if re.search(r"\.(?:jpg|jpeg|png|webp|avif)(?:\?|$)", low) or any(
                    host in low for host in (
                        "cloudinary", "shopify", "trendyol", "hepsiburada", "n11", "amazon",
                        "migros", "carrefoursa", "a101", "sokmarket", "imagedelivery.net",
                        "cdn", "static", "media"
                    )
                ):
                    if u not in originals:
                        originals.append(u)

        # Google sonuç sayfasındaki küçük görseller: özgün URL hiç yoksa yedek.
        for found in re.findall(r'''<img[^>]+(?:src|data-src)=["'](https?://[^"']+)["']''', normalized, flags=re.I):
            u = _v69_decode_url(found)
            low = u.lower()
            if "encrypted-tbn" in low or "gstatic.com/images?q=tbn" in low:
                if u not in thumbnails:
                    thumbnails.append(u)

    return originals[:30] + thumbnails[:20]


def _v69_download_image_bytes(url: str, timeout: int = 22) -> bytes:
    headers = _v69_google_headers(True)
    headers["Referer"] = "https://www.google.com/"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read(14 * 1024 * 1024)


def _v69_cache_path(barcode: str) -> str:
    safe = re.sub(r"[^0-9A-Za-z_.-]+", "_", str(barcode or "urun"))
    return os.path.join(v67._v67_cache_dir(), "google_v69_" + safe + ".png")


def _v69_download_google_image(product_name: str, barcode: str):
    if not PIL_OK:
        return None, ""

    cache = _v69_cache_path(barcode)
    if os.path.isfile(cache):
        try:
            return Image.open(cache).convert("RGBA"), "Google Görseller"
        except Exception:
            pass

    queries = []
    for q in (
        " ".join(x for x in (str(product_name or "").strip(), str(barcode or "").strip()) if x),
        str(barcode or "").strip(),
        str(product_name or "").strip(),
    ):
        if q and q not in queries:
            queries.append(q)

    all_candidates: List[str] = []
    for q in queries:
        try:
            for u in _v69_google_candidates(q):
                if u not in all_candidates:
                    all_candidates.append(u)
            if all_candidates:
                break
        except Exception:
            pass

    for image_url in all_candidates[:35]:
        try:
            raw = _v69_download_image_bytes(image_url)
            if not raw or len(raw) < 1500:
                continue
            img = Image.open(io.BytesIO(raw)).convert("RGBA")
            if img.width < 70 or img.height < 70:
                continue
            img = v67._v67_remove_background(img)
            if img is None:
                continue
            try:
                img.save(cache, "PNG", optimize=True)
            except Exception:
                pass
            return img, "Google Görseller"
        except Exception:
            continue

    # Son çare: önceki ToptanTR/OpenFoodFacts motoru.
    try:
        return v67._v67_download_product_image(barcode)
    except Exception:
        return None, ""


def _v69_start_product_image(self, barcode: str):
    digits = re.sub(r"\D+", "", str(barcode or ""))
    if not digits:
        return
    try:
        product_name = (self.ent_stokadi.get() or "").strip()
    except Exception:
        product_name = ""

    self._v67_image_token = int(getattr(self, "_v67_image_token", 0)) + 1
    token = self._v67_image_token
    v67._v67_set_image_status(
        self,
        "GOOGLE GÖRSELLER'DE ARANIYOR...\n" + (product_name or digits),
    )

    def worker():
        image, source = _v69_download_google_image(product_name, digits)
        try:
            self.after(0, lambda: v67._v67_apply_product_image(self, token, image, source))
        except Exception:
            pass

    threading.Thread(target=worker, daemon=True).start()


# =============================================================================
# 4) DASHBOARD BAŞLARKEN STOK KODUNU YAKALA + V69 GOOGLE MOTORUNU ÇALIŞTIR
# =============================================================================
def _v69_load_product_dashboard(self, barcode: Optional[str] = None):
    b = (barcode or (self.ent_barkod.get() if hasattr(self, "ent_barkod") else "") or "").strip()
    if not b:
        self._clear_dashboard()
        return

    try:
        self._v69_dashboard_stock_code = (self.ent_stokkod.get() or "").strip()
    except Exception:
        self._v69_dashboard_stock_code = ""

    # V65'in orijinal yükleme akışı, ancak worker artık V69 worker'dır.
    result = v67._ORIG_LOAD_PRODUCT_DASHBOARD(self, b)
    _v69_start_product_image(self, b)
    return result


base.App.load_product_dashboard = _v69_load_product_dashboard


if __name__ == "__main__":
    login_app = base.LoginWindow()
    login_app.mainloop()
