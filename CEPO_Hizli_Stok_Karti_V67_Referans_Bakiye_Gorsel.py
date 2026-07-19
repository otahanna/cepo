# -*- coding: utf-8 -*-
"""
CEPO Hızlı Stok Kartı V67
- V65 ana dosyasının tüm stok kartı / çift veritabanı özelliklerini korur.
- Şube/depo bakiyesini CEPO_SIPARIS V1196 referansındaki gerçek mantıkla getirir:
    SELECT DEPOID, SUM(MIKTAR) ... GROUP BY DEPOID
- Alt şube tablosu: DB | Şube/Depo | Bakiye | Son Maliyet | Tutar | Son Hareket
- Sağ panelde Toplam Giriş / Toplam Çıkış kaldırılır; Toplam Tutar gösterilir.
- Toplam stok ve şube stokları ekranda seçili (Görüntüle / Düzenle) veritabanına göre gösterilir.
- Kusuratsız miktarlar tam sayı görünür.
- Ürün görseli barkodla otomatik olarak ToptanTR üzerinden aranır; OpenFoodFacts yedektir.
- Görsel mümkünse rembg ile, yoksa kenar tabanlı yöntemle arka plansız hale getirilir.

KULLANIM:
Bu dosyayı CEPO_Hizli_Stok_Karti_V65_Referans_Profesyonel.py ile aynı klasöre koyun ve V67'yi çalıştırın.
"""

from __future__ import annotations

import os
import sys
import io
import re
import json
import math
import html
import threading
import importlib.util
import urllib.parse
import urllib.request
from collections import deque
from typing import Any, Dict, List, Optional, Tuple

BASE_FILE = "CEPO_Hizli_Stok_Karti_V65_Referans_Profesyonel.py"
HERE = os.path.dirname(os.path.abspath(__file__))
BASE_PATH = os.path.join(HERE, BASE_FILE)

if not os.path.isfile(BASE_PATH):
    raise SystemExit(
        "Gerekli ana dosya bulunamadı:\n"
        + BASE_PATH
        + "\n\nV65 dosyası ile V67 dosyasını aynı klasöre koyun."
    )

spec = importlib.util.spec_from_file_location("cepo_hizli_stok_v65_base", BASE_PATH)
if spec is None or spec.loader is None:
    raise SystemExit("V65 ana modülü yüklenemedi.")
base = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = base
spec.loader.exec_module(base)

base.APP_TITLE = "CEPO Hızlı Stok Kartı V67"

try:
    from PIL import Image
    PIL_OK = True
except Exception:
    Image = None
    PIL_OK = False

try:
    from rembg import remove as _rembg_remove
except Exception:
    _rembg_remove = None


# =============================================================================
# SAYI FORMATLAMA
# =============================================================================
def _v67_fmt_number(self, value: Any, decimals: int = 2) -> str:
    try:
        n = float(value or 0)
    except Exception:
        return ""
    if not math.isfinite(n):
        return ""
    if abs(n - round(n)) < 1e-9:
        return f"{int(round(n)):,}".replace(",", ".")
    raw = f"{n:,.{max(0, int(decimals))}f}"
    if "." in raw:
        raw = raw.rstrip("0").rstrip(".")
    return raw.replace(",", "X").replace(".", ",").replace("X", ".")


def _v67_fmt_money(self, value: Any) -> str:
    try:
        n = float(value or 0)
    except Exception:
        n = 0.0
    s = f"{n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return s + " ₺"


base.App._fmt_number = _v67_fmt_number
base.App._fmt_money = _v67_fmt_money


# =============================================================================
# GERÇEK BAKİYE + STOK KARTI SON MALİYETİ
# Referans:
#   SELECT DEPOID, SUM(MIKTAR) FROM TBL_STOK_HAREKET WHERE STOKID=? GROUP BY DEPOID
#   Tutar = Bakiye * Son Maliyet
# =============================================================================
_ORIG_GET_STOCK_DASHBOARD = base.DBAdapter.get_stock_dashboard


def _v67_get_stock_cost(adapter, stock_id: int) -> float:
    if not adapter.cn or not stock_id:
        return 0.0
    try:
        cols = adapter._table_cols(base.MAIN_TABLE)
        candidates = [
            "SONMALIYETFIYATI",
            "MALIYETFIYATI",
            "SONALISFIYATI",
            "ALISFIYATI",
        ]
        present = [c for c in candidates if c in cols]
        if present:
            expr = "COALESCE(" + ",".join(present) + ",0)"
            cur = adapter.cn.cursor()
            cur.execute(f"SELECT TOP 1 {expr} FROM {base.MAIN_TABLE} WITH (NOLOCK) WHERE ID=?", (int(stock_id),))
            row = cur.fetchone()
            if row:
                return float(row[0] or 0)
    except Exception:
        pass

    # Bazı kurulumlarda maliyet ayrı tabloda tutulur; yalnızca stok kartı kolonları yoksa yedek.
    try:
        cols = adapter._table_cols("dbo.TBL_STOK_MALIYET")
        if cols and "STOKID" in cols and "FIYAT" in cols:
            cur = adapter.cn.cursor()
            order_col = "ID" if "ID" in cols else ("CHANGEDATE" if "CHANGEDATE" in cols else None)
            order_sql = f" ORDER BY {order_col} DESC" if order_col else ""
            cur.execute(
                f"SELECT TOP 1 FIYAT FROM dbo.TBL_STOK_MALIYET WITH (NOLOCK) WHERE STOKID=?{order_sql}",
                (int(stock_id),),
            )
            row = cur.fetchone()
            if row:
                return float(row[0] or 0)
    except Exception:
        pass
    return 0.0


def _v67_get_stock_dashboard(self, stock_id: int, db_name: str) -> Dict[str, Any]:
    # Alış/satış/transfer hareketleri ve tarihler V65 motorundan gelsin.
    result = _ORIG_GET_STOCK_DASHBOARD(self, stock_id, db_name)
    if not self.cn or not stock_id:
        return result

    try:
        hcols = self._table_cols(base.HAREKET_TABLE)
        h_stok = self._first_existing(hcols, ["STOKID", "STOKKARTID", "STOK_ID"])
        h_qty = self._first_existing(hcols, ["MIKTAR", "ADET", "MIK", "QTY", "MIKTAR1"])
        h_depo = self._first_existing(hcols, ["DEPOID"])
        h_date = self._first_existing(hcols, ["BELGETARIHI", "TARIH", "ISLEMTARIHI", "CREATEDATE"])
        if not h_stok or not h_qty or not h_depo:
            return result

        cost = _v67_get_stock_cost(self, int(stock_id))
        depo_map = self._id_name_map(
            base.DEPO_TABLE,
            ["DEPOADI", "DEPO_ADI", "ACIKLAMA", "ADI", "ISIM", "TANIM"],
        )
        sube_map = self._id_name_map(
            base.SUBE_TABLE,
            ["SUBEADI", "SUBE_ADI", "ACIKLAMA", "ADI", "ISIM", "TANIM"],
        )

        cur = self.cn.cursor()
        date_expr = f"MAX(H.{h_date})" if h_date else "NULL"
        cur.execute(
            f"""
            SELECT
                H.{h_depo},
                COALESCE(SUM(CAST(H.{h_qty} AS FLOAT)), 0) AS BAKIYE,
                {date_expr} AS SON_HAREKET
            FROM {base.HAREKET_TABLE} H WITH (NOLOCK)
            WHERE H.{h_stok}=?
            GROUP BY H.{h_depo}
            ORDER BY H.{h_depo}
            """,
            (int(stock_id),),
        )

        branches: List[Dict[str, Any]] = []
        total_balance = 0.0
        for depo_id, balance, last_date in cur.fetchall():
            try:
                did = int(depo_id) if depo_id is not None else None
            except Exception:
                did = None
            bal = float(balance or 0)
            total_balance += bal
            location = depo_map.get(did) or sube_map.get(did) or (str(depo_id) if depo_id is not None else "")
            branches.append(
                {
                    "db": str(db_name or "").upper(),
                    "location": location,
                    "balance": bal,
                    "last_cost": cost,
                    "amount": bal * cost,
                    "last_date": last_date,
                }
            )

        result["branches"] = branches
        summary = result.setdefault("summary", {})
        summary["balance"] = total_balance
        summary["last_cost"] = cost
        summary["stock_amount"] = total_balance * cost
    except Exception as exc:
        try:
            base.debug_print(f"V67 gerçek bakiye sorgusu uygulanamadı ({db_name}): {exc}")
        except Exception:
            pass
    return result


base.DBAdapter.get_stock_dashboard = _v67_get_stock_dashboard


# =============================================================================
# ARAYÜZ: GİREN / ÇIKAN KALKSIN, BAKİYE + SON MALİYET + TUTAR GELSİN
# =============================================================================
_ORIG_SETUP_UI = base.App.setup_ui


def _v67_change_box_title(value_label, new_title: str) -> None:
    try:
        box = value_label.master
        for child in box.winfo_children():
            if child is value_label:
                continue
            try:
                txt = str(child.cget("text") or "")
            except Exception:
                txt = ""
            if txt:
                child.configure(text=new_title)
                break
    except Exception:
        pass


def _v67_setup_ui(self):
    _ORIG_SETUP_UI(self)

    # Alt şube tablosu referans stok kartıyla aynı bilgi düzeninde.
    try:
        cols = ("db", "location", "bakiye", "maliyet", "tutar", "son")
        self.branch_tree.configure(columns=cols, displaycolumns=cols)
        heads = {
            "db": "DB",
            "location": "Şube / Depo",
            "bakiye": "Bakiye",
            "maliyet": "Son Maliyet",
            "tutar": "Tutar",
            "son": "Son Hareket",
        }
        widths = {"db": 70, "location": 360, "bakiye": 150, "maliyet": 160, "tutar": 180, "son": 170}
        for c in cols:
            self.branch_tree.heading(c, text=heads[c])
            self.branch_tree.column(c, width=widths[c], anchor="w" if c in ("db", "location") else "e")
    except Exception:
        pass

    # Sağ panelde giriş/çıkış yerine toplam tutar.
    try:
        in_lbl = self.summary_labels.get("in")
        out_lbl = self.summary_labels.get("out")
        if in_lbl is not None:
            _v67_change_box_title(in_lbl, "TOPLAM TUTAR")
            self.summary_labels["amount"] = in_lbl
            try:
                in_lbl.master.grid_configure(columnspan=2)
            except Exception:
                pass
        if out_lbl is not None:
            try:
                out_lbl.master.grid_remove()
            except Exception:
                pass
        last_cost_lbl = self.summary_labels.get("last_cost")
        if last_cost_lbl is not None:
            _v67_change_box_title(last_cost_lbl, "SON MALİYET")
    except Exception:
        pass

    self._v67_image_token = 0
    self._v67_ctk_product_image = None


base.App.setup_ui = _v67_setup_ui


# =============================================================================
# RENDER: STOK TABLOSU VE TOPLAM STOK SEÇİLİ DB'YE GÖRE
# =============================================================================
_ORIG_RENDER_DASHBOARD = base.App._render_dashboard


def _v67_render_dashboard(self, barcode: str, token: int, dashboards: List[Dict[str, Any]], errors: List[str]):
    # Hareket tablosu / filtreler / istatistikler V65 tarafından çizilsin.
    _ORIG_RENDER_DASHBOARD(self, barcode, token, dashboards, errors)
    if token != getattr(self, "_dashboard_token", token):
        return

    try:
        target_db = str(self.cmb_target_db.get() or "").strip().lower()
    except Exception:
        target_db = ""

    selected = [d for d in dashboards if str(d.get("db") or "").strip().lower() == target_db]
    if not selected:
        selected = dashboards

    try:
        for iid in self.branch_tree.get_children():
            self.branch_tree.delete(iid)
    except Exception:
        pass

    total_balance = 0.0
    total_amount = 0.0
    selected_cost = 0.0
    last_purchase = None
    last_sale = None
    branch_count = 0

    for dash in selected:
        sm = dash.get("summary", {}) or {}
        cost = float(sm.get("last_cost") or 0)
        balance = float(sm.get("balance") or 0)
        amount = float(sm.get("stock_amount") or (balance * cost))
        total_balance += balance
        total_amount += amount
        selected_cost = cost
        lp = sm.get("last_purchase")
        ls = sm.get("last_sale")
        if lp and (last_purchase is None or lp > last_purchase):
            last_purchase = lp
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
                        br.get("db", ""),
                        br.get("location", ""),
                        self._fmt_number(bal, 3),
                        self._fmt_money(br_cost),
                        self._fmt_money(br_amount),
                        self._fmt_date(br.get("last_date"), True),
                    ),
                )
            except Exception:
                pass

    # Sağ panel: seçili DB'nin gerçek bakiyesi ve maliyeti.
    try:
        self.summary_labels["balance"].configure(text=self._fmt_number(total_balance, 3))
    except Exception:
        pass
    try:
        self.summary_labels["last_cost"].configure(text=self._fmt_money(selected_cost) if selected_cost else "—")
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

    # Kârlılık da seçili DB'nin son maliyetini baz alsın.
    try:
        sale_price = float(str(self.ent_fiyat.get() or "0").replace(",", "."))
    except Exception:
        sale_price = 0.0
    profit_value = sale_price - selected_cost
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
        db_text = ", ".join(str(d.get("db") or "") for d in selected) or "Kayıt bulunamadı"
        self.lbl_dashboard_info.configure(
            text=f"{barcode} • {db_text} • {branch_count} şube/depo • gerçek SUM(MIKTAR) bakiyesi"
        )
    except Exception:
        pass


base.App._render_dashboard = _v67_render_dashboard


# =============================================================================
# OTOMATİK ÜRÜN GÖRSELİ - REFERANS CEPO V735 / TOPTANTR AKIŞI
# =============================================================================
TOPTANTR_BASE = "https://www.toptantr.com"


def _v67_headers(accept_image: bool = False, referer: str = "") -> Dict[str, str]:
    h = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36 "
            "CEPO-Hizli-Stok/67"
        ),
        "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.7,en;q=0.6",
        "Connection": "close",
    }
    if accept_image:
        h["Accept"] = "image/jpeg,image/png,image/webp,image/apng,image/*;q=0.9,*/*;q=0.5"
    else:
        h["Accept"] = "text/html,application/xhtml+xml,application/json,application/xml;q=0.9,*/*;q=0.8"
    if referer:
        h["Referer"] = referer
    return h


def _v67_fetch_bytes(url: str, timeout: int = 22, accept_image: bool = False, referer: str = "") -> Tuple[bytes, str, str]:
    req = urllib.request.Request(url, headers=_v67_headers(accept_image=accept_image, referer=referer))
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read(12 * 1024 * 1024)
        final_url = resp.geturl()
        ctype = str(resp.headers.get("Content-Type") or "")
    return data, final_url, ctype


def _v67_fetch_text(url: str, timeout: int = 22) -> Tuple[str, str]:
    data, final_url, ctype = _v67_fetch_bytes(url, timeout=timeout, accept_image=False)
    enc = "utf-8"
    m = re.search(r"charset=([\w\-]+)", ctype, re.I)
    if m:
        enc = m.group(1)
    try:
        text = data.decode(enc, errors="replace")
    except Exception:
        text = data.decode("utf-8", errors="replace")
    return text, final_url


def _v67_strip_tags(s: str) -> str:
    s = re.sub(r"(?is)<script.*?</script>", " ", str(s or ""))
    s = re.sub(r"(?is)<style.*?</style>", " ", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def _v67_norm_url(url: str) -> str:
    u = html.unescape(str(url or "")).replace("\\/", "/").replace("\\u002F", "/").strip()
    if u.startswith("//"):
        u = "https:" + u
    return urllib.parse.urljoin(TOPTANTR_BASE, u)


def _v67_full_variant(url: str) -> str:
    u = _v67_norm_url(url).replace("\\", "")
    parsed = urllib.parse.urlparse(u)
    if "imagedelivery.net" in parsed.netloc:
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) >= 2:
            path = "/" + "/".join(parts[:2] + ["full"])
            u = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))
    return u


def _v67_find_product_url(search_html: str, final_url: str) -> Optional[str]:
    if "/search-e" not in str(final_url or "") and re.search(r"/\d+[-/]", str(final_url or "")):
        return final_url
    for href in re.findall(r'''href\s*=\s*["']([^"']+)["']''', search_html or "", flags=re.I):
        u = _v67_norm_url(href).split("#")[0]
        parsed = urllib.parse.urlparse(u)
        if re.match(r"^/\d+[-/][^/]+", parsed.path or "") and "toptantr.com" in parsed.netloc:
            return u
    return None


def _v67_extract_image_urls(product_html: str, barcode: str) -> List[str]:
    low = (product_html or "").lower()
    pos_barcode = low.find(str(barcode or "").lower())
    pos_h1 = low.find("<h1")
    segments: List[str] = []
    if pos_barcode >= 0:
        segments.append(product_html[max(0, pos_barcode - 45000): min(len(product_html), pos_barcode + 9000)])
    if pos_h1 >= 0:
        segments.append(product_html[max(0, pos_h1 - 45000): min(len(product_html), pos_h1 + 9000)])
    segments.append(product_html)

    patterns = [
        r'''href\s*=\s*["']([^"']*imagedelivery\.net[^"']+)["']''',
        r'''src\s*=\s*["']([^"']*imagedelivery\.net[^"']+)["']''',
        r'''data-src\s*=\s*["']([^"']*imagedelivery\.net[^"']+)["']''',
        r'''data-large\s*=\s*["']([^"']*imagedelivery\.net[^"']+)["']''',
        r'''data-zoom-image\s*=\s*["']([^"']*imagedelivery\.net[^"']+)["']''',
        r'''https?:\\?/\\?/imagedelivery\.net\\?/[^"'\s<>)]+''',
        r'''https?://imagedelivery\.net/[^"'\s<>)]+''',
        r'''//imagedelivery\.net/[^"'\s<>)]+''',
        r'''<meta[^>]+property=["']og:image["'][^>]+content=["']([^"']+)["']''',
        r'''<meta[^>]+content=["']([^"']+)["'][^>]+property=["']og:image["']''',
    ]
    out: List[str] = []
    for seg in segments:
        for pat in patterns:
            for match in re.findall(pat, seg or "", flags=re.I):
                u = _v67_full_variant(match)
                low_u = u.lower()
                if any(x in low_u for x in ("logo", "favicon", "icon", "banner", "whatsapp", "facebook", "instagram", "youtube")):
                    continue
                if u and u not in out:
                    out.append(u)
        if out:
            break
    return out


def _v67_toptantr_candidates(barcode: str) -> Tuple[List[str], str]:
    digits = re.sub(r"\D+", "", str(barcode or ""))
    if not digits:
        return [], ""
    search_url = TOPTANTR_BASE + "/search-e?q=" + urllib.parse.quote(digits)
    search_html, final_url = _v67_fetch_text(search_url)
    product_url = _v67_find_product_url(search_html, final_url)
    if not product_url:
        return [], ""
    product_html, product_final = _v67_fetch_text(product_url)
    product_url = product_final or product_url
    plain = _v67_strip_tags(product_html)
    if digits not in plain:
        # Barkod doğrulanamazsa yanlış ürün resmi göstermeyelim.
        return [], product_url
    return _v67_extract_image_urls(product_html, digits), product_url


def _v67_openfoodfacts_candidates(barcode: str) -> List[str]:
    digits = re.sub(r"\D+", "", str(barcode or ""))
    if not digits:
        return []
    try:
        url = "https://world.openfoodfacts.org/api/v2/product/" + urllib.parse.quote(digits) + ".json"
        data, _, _ = _v67_fetch_bytes(url, timeout=12, accept_image=False)
        obj = json.loads(data.decode("utf-8", errors="ignore"))
        prod = obj.get("product") or {}
        urls = []
        for key in ("image_front_url", "image_url", "image_front_small_url"):
            u = str(prod.get(key) or "").strip()
            if u and u not in urls:
                urls.append(u)
        return urls
    except Exception:
        return []


def _v67_cache_dir() -> str:
    root = os.environ.get("LOCALAPPDATA") or HERE
    path = os.path.join(root, "CEPO", "urun_gorsel_cache")
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        path = os.path.join(HERE, "urun_gorsel_cache")
        os.makedirs(path, exist_ok=True)
    return path


def _v67_cache_path(barcode: str) -> str:
    safe = re.sub(r"[^0-9A-Za-z_.-]+", "_", str(barcode or "urun"))
    return os.path.join(_v67_cache_dir(), safe + ".png")


def _v67_simple_remove_background(img):
    if not PIL_OK or img is None:
        return img
    image = img.convert("RGBA")
    # Çok büyük görsellerde temizleme hızını koru.
    if max(image.size) > 1100:
        image.thumbnail((1100, 1100), Image.LANCZOS)

    w, h = image.size
    if w < 3 or h < 3:
        return image
    px = image.load()
    corners = [px[0, 0], px[w - 1, 0], px[0, h - 1], px[w - 1, h - 1]]
    bg = tuple(sum(int(c[i]) for c in corners) / len(corners) for i in range(3))

    def dist(p):
        return ((p[0] - bg[0]) ** 2 + (p[1] - bg[1]) ** 2 + (p[2] - bg[2]) ** 2) ** 0.5

    threshold = 52.0
    q = deque()
    visited = bytearray(w * h)
    for x in range(w):
        q.append((x, 0)); q.append((x, h - 1))
    for y in range(h):
        q.append((0, y)); q.append((w - 1, y))

    while q:
        x, y = q.popleft()
        idx = y * w + x
        if visited[idx]:
            continue
        visited[idx] = 1
        p = px[x, y]
        if p[3] <= 8 or dist(p) <= threshold:
            px[x, y] = (p[0], p[1], p[2], 0)
            if x > 0: q.append((x - 1, y))
            if x + 1 < w: q.append((x + 1, y))
            if y > 0: q.append((x, y - 1))
            if y + 1 < h: q.append((x, y + 1))

    bbox = image.getbbox()
    if bbox:
        image = image.crop(bbox)
    return image


def _v67_remove_background(img):
    if not PIL_OK or img is None:
        return img
    if _rembg_remove is not None:
        try:
            out = _rembg_remove(img.convert("RGBA"))
            if hasattr(out, "convert"):
                return out.convert("RGBA")
        except Exception:
            pass
    return _v67_simple_remove_background(img)


def _v67_prepare_display_image(img):
    if not PIL_OK or img is None:
        return img
    image = img.convert("RGBA")
    image.thumbnail((260, 260), Image.LANCZOS)
    canvas = Image.new("RGBA", (280, 280), (255, 255, 255, 0))
    x = (280 - image.width) // 2
    y = (280 - image.height) // 2
    canvas.alpha_composite(image, (x, y))
    return canvas


def _v67_download_product_image(barcode: str):
    if not PIL_OK:
        return None, ""

    cache = _v67_cache_path(barcode)
    if os.path.isfile(cache):
        try:
            return Image.open(cache).convert("RGBA"), "Önbellek"
        except Exception:
            pass

    candidates: List[Tuple[str, str]] = []
    try:
        urls, product_url = _v67_toptantr_candidates(barcode)
        candidates.extend((u, product_url) for u in urls)
    except Exception:
        pass
    for u in _v67_openfoodfacts_candidates(barcode):
        candidates.append((u, "https://world.openfoodfacts.org/"))

    seen = set()
    for url, referer in candidates:
        if not url or url in seen:
            continue
        seen.add(url)
        try:
            data, _, ctype = _v67_fetch_bytes(url, timeout=20, accept_image=True, referer=referer)
            if not data:
                continue
            img = Image.open(io.BytesIO(data)).convert("RGBA")
            img = _v67_remove_background(img)
            if img is None:
                continue
            try:
                img.save(cache, "PNG", optimize=True)
            except Exception:
                pass
            return img, "ToptanTR" if "toptantr" in str(referer).lower() else "OpenFoodFacts"
        except Exception:
            continue
    return None, ""


def _v67_set_image_status(self, text: str):
    try:
        self.lbl_product_visual.configure(image=None, text=text)
    except Exception:
        try:
            self.lbl_product_visual.configure(text=text)
        except Exception:
            pass


def _v67_apply_product_image(self, token: int, image, source: str):
    if token != getattr(self, "_v67_image_token", token):
        return
    if image is None:
        _v67_set_image_status(self, "ÜRÜN GÖRSELİ BULUNAMADI\nWeb'de Ara ile manuel kontrol edebilirsiniz")
        return
    try:
        display = _v67_prepare_display_image(image)
        ctk_img = base.ctk.CTkImage(light_image=display, dark_image=display, size=(260, 260))
        self._v67_ctk_product_image = ctk_img
        self.lbl_product_visual.configure(image=ctk_img, text="")
        try:
            self.lbl_product_name.configure(text=(self.ent_stokadi.get() or "") + (f"  •  {source}" if source else ""))
        except Exception:
            pass
    except Exception as exc:
        _v67_set_image_status(self, "Görsel yüklenemedi")
        try:
            base.debug_print(f"V67 ürün görseli ekrana basılamadı: {exc}")
        except Exception:
            pass


def _v67_start_product_image(self, barcode: str):
    digits = re.sub(r"\D+", "", str(barcode or ""))
    if not digits:
        return
    self._v67_image_token = int(getattr(self, "_v67_image_token", 0)) + 1
    token = self._v67_image_token
    _v67_set_image_status(self, "ÜRÜN GÖRSELİ ARANIYOR...\n" + digits)

    def worker():
        image, source = _v67_download_product_image(digits)
        try:
            self.after(0, lambda: _v67_apply_product_image(self, token, image, source))
        except Exception:
            pass

    threading.Thread(target=worker, daemon=True).start()


_ORIG_LOAD_PRODUCT_DASHBOARD = base.App.load_product_dashboard


def _v67_load_product_dashboard(self, barcode: Optional[str] = None):
    b = (barcode or (self.ent_barkod.get() if hasattr(self, "ent_barkod") else "") or "").strip()
    result = _ORIG_LOAD_PRODUCT_DASHBOARD(self, barcode)
    if b:
        _v67_start_product_image(self, b)
    return result


base.App.load_product_dashboard = _v67_load_product_dashboard

_ORIG_CLEAR_DASHBOARD = base.App._clear_dashboard


def _v67_clear_dashboard(self):
    result = _ORIG_CLEAR_DASHBOARD(self)
    self._v67_image_token = int(getattr(self, "_v67_image_token", 0)) + 1
    self._v67_ctk_product_image = None
    try:
        self.lbl_product_visual.configure(
            image=None,
            text="▦\n\nÜRÜN GÖRSELİ\nBarkod okutulduğunda otomatik bulunur",
        )
    except Exception:
        pass
    return result


base.App._clear_dashboard = _v67_clear_dashboard


if __name__ == "__main__":
    login_app = base.LoginWindow()
    login_app.mainloop()
