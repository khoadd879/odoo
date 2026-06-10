# ODOO — DEMO LINKS (live + video) cho người xem

Cập nhật: 2026-06-09

---

## 🟢 LIVE DEMO (click vào dùng ngay)

### 1. Odoo official demo (Enterprise, full data)
**👉 https://demo.odoo.com** — auto-redirect tới instance mới nhất, login sẵn với admin/demo data. Mỗi vài giờ reset.

Có 2 version:
- **Runbot preview** (master branch, dev unstable): https://runbot.odoo.com
- **SaaS demo** (stable, polished): https://demo.odoo.com → sang `demo2.odoo.com/saas_worker/demo`

→ Best for: show "real" Odoo không cần cài

### 2. OCA Runboat — Test OCA modules trực tiếp
**👉 https://runboat.odoo-community.org** — 240 OCA repos sẵn sandbox

Cách dùng: Vào `https://runboat.odoo-community.org/builds?repo=OCA/<repo>&target_branch=18.0` → trigger build → URL riêng cho instance Odoo chạy module đó. Vd:

- Geospatial (bản đồ): https://runboat.odoo-community.org/builds?repo=OCA/geospatial&target_branch=18.0
- DDMRP: https://runboat.odoo-community.org/builds?repo=OCA/ddmrp&target_branch=18.0
- Commission: https://runboat.odoo-community.org/builds?repo=OCA/commission&target_branch=18.0
- WMS bundle: https://runboat.odoo-community.org/builds?repo=OCA/wms&target_branch=18.0
- Helpdesk: https://runboat.odoo-community.org/builds?repo=OCA/helpdesk&target_branch=18.0
- Vertical hotel: https://runboat.odoo-community.org/builds?repo=OCA/vertical-hotel&target_branch=18.0
- MIS Builder: https://runboat.odoo-community.org/builds?repo=OCA/mis-builder&target_branch=18.0

→ Best for: demo OCA modules cụ thể mà không cần cài

### 3. Bản của bạn — `company20_vn` (đang chạy port 8069)
**👉 http://localhost:8069** — đã có 21 employees, 25 products, 8 KH, 3 NCC, 350 inventory, 2 SO paid. 

→ Best for: show data **tiếng Việt** thực tế của công ty mình

### 4. Odoo free trial (Enterprise, 15 ngày)
**👉 https://www.odoo.com/trial** — chọn apps, có data mẫu, dùng full features

→ Best for: show EE-only (Spreadsheet Dashboard, Field Service, Sign, Helpdesk, Planning, Documents OCR)

---

## 🎬 VIDEO SHOWCASE (công bố chính thức từ Odoo)

### Odoo Experience 2025 (conference Brussels, Sep 2025)
**👉 https://www.odoo.com/event/odoo-experience-2025-6601/track**

Có 469 session links. Những cái **nổi bật** (master class + keynotes):

| Topic | Link |
|---|---|
| **Odoo AI** master class | https://www.odoo.com/event/odoo-experience-2025-6601/track/master-class-odoo-ai-7413 |
| **Advanced Dashboards & Spreadsheets** | https://www.odoo.com/event/odoo-experience-2025-6601/track/master-class-advanced-dashboards-spreadsheets-7405 |
| **Advanced Manufacturing** | https://www.odoo.com/event/odoo-experience-2025-6601/track/master-class-advanced-manufacturing-7399 |
| **Advanced Accounting** | https://www.odoo.com/event/odoo-experience-2025-6601/track/master-class-advanced-accounting-7397 |
| **Odoo Web Framework** | https://www.odoo.com/event/odoo-experience-2025-6601/track/master-class-odoo-web-framework-7396 |
| **Scaling Odoo** | https://www.odoo.com/event/odoo-experience-2025-6601/track/master-class-scaling-odoo-7407 |
| **Introduction to Development** | https://www.odoo.com/event/odoo-experience-2025-6601/track/master-class-introduction-to-development-7398 |

Introduction video OXP25 (YouTube embeds): `fXTQesmhQ_4`, `0f9pGxaXWz0` trên https://www.odoo.com/event/odoo-experience-2025-6601

### Odoo YouTube channel
**👉 https://www.youtube.com/@Odoo**

Search "Odoo 19 demo", "Odoo 19 features", "Odoo AI" — có 145+ videos cập nhật.

### Odoo eLearning (miễn phí, do Odoo maintain)
**👉 https://www.odoo.com/slides** — slides bài giảng từng module

### Odoo Podcasts & Webinars
- Podcast: https://podcast.odoo.com
- Webinars: https://www.odoo.com/page/webinars
- Odoo TV (FM radio style): https://www.odoo.fm

---

## 🎯 TIPS DEMO

### Setup trước 1 giờ
1. Mở `https://demo.odoo.com` → login sẵn → bookmark 5 app hay show: Sales, Inventory, Manufacturing, Accounting, Spreadsheet Dashboard
2. Mở `http://localhost:8069` (DB `company20_vn` của bạn) — backup data là data VN thật
3. Mở 1-2 OCA Runboat (Geospatial, DDMRP) → so sánh CE vs OCA
4. Có EE trial → show Spreadsheet Dashboard, Sign, Helpdesk

### Kịch bản demo 30 phút (gợi ý)
- 0-3': Odoo Experience 2025 intro video (`fXTQesmhQ_4`)
- 3-8': Show localhost `company20_vn` — 1 SO hoàn chỉnh từ quote → invoice → payment
- 8-13': Show Manufacturing (BOM → MO → Work Order) trên demo.odoo.com
- 13-18': Show Spreadsheet Dashboard (EE) — KPI real-time
- 18-23': Show OCA Geospatial (Runboat) — KH trên bản đồ Leaflet
- 23-28': Show `l10n_vn_edi_viettel` (đã có sẵn trong localhost) — đẩy hóa đơn Viettel
- 28-30': Q&A + link `ODOO_DEMO_FEATURES.md`

### Kịch bản demo 60 phút (full)
- Thêm 5': Odoo AI master class (`master-class-odoo-ai-7413`) video clip
- Thêm 5': POS Self-Order QR (mobile scan)
- Thêm 5': Event + Live broadcast
- Thêm 5': eInvoicing VN
- Thêm 10': Custom Q&A theo audience

---

## 📋 CHECKLIST KHI DEMO

- [ ] Test load demo.odoo.com từ browser trước 1h (CDN chậm khi OXP công bố)
- [ ] Có backup link localhost (nếu internet rớt)
- [ ] Có sẵn video offline (download YouTube trước bằng `yt-dlp`)
- [ ] Mở `ODOO_DEMO_FEATURES.md` để dẫn link nhanh khi ai hỏi
- [ ] Pre-load OCA Runboat trước 5' (build chậm)
- [ ] Bookmark Odoo Experience 2025 track page để drill vào session cụ thể

---

File này: `/home/khoa/Company/odoo/ODOO_DEMO_LINKS.md`
