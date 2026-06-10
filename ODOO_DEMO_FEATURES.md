# ODOO — Tính năng "wow" để DEMO (ngoài Ecommerce & AI)

Cập nhật: 2026-06-09 · Stack: Odoo 18 CE @ `/home/khoa/Company/odoo`

Mục đích: catalog tính năng ấn tượng nhất của Odoo để show cho người xem. Chia thành 6 nhóm, mỗi mục có **link apps.odoo.com hoặc GitHub** để mở demo. Tính năng CE = có sẵn trong DB `company20_vn`, EE = cần mua Enterprise, OCA = free community add-on.

---

## 1) BÁN HÀNG & POS — "wow" nhất

### 🍽️ **POS Restaurant** (CE) — Order từ bàn, kitchen display, tip
- **Bản chất**: Odoo POS thông thường + thêm flow nhà hàng
- **Demo gì**: 
  - Mở POS → chọn bàn số 5 → tablet order cho khách → gửi xuống **Kitchen Display** (màn hình bếp) theo category (đồ uống/bar, đồ nóng/kitchen)
  - Tách bill theo món, tip cho nhân viên, in bill 2 bản
  - Floor plan visual (sơ đồ bàn kéo thả)
- **EE-only module mở rộng**: `pos_cashdro` (máy đếm tiền tự động), `pos_self_order_kiosk` (QR-code khách tự order)
- **Link**: https://odoo.com/app/point-of-sale-restaurant

### 📱 **POS Self Order / Kiosk** (CE) — Khách tự order bằng QR code
- **Bản chất**: Khách quét QR → menu → order → thanh toán → nhận số
- **Demo gì**: Mở app/web trên điện thoại → thấy menu giống foodpanda → chọn Burger + Coke → trả qua Stripe → bếp tự nhận đơn
- **Pay**: tích hợp Stripe, Adyen, Pine Labs, Mercado Pago, Razorpay, Viva, QFPay
- **Use case**: quán cafe, fast-food, kiosk sân bay

### 🎁 **Loyalty & Promotion Engine** (CE) — Tích điểm, voucher, coupon
- **Demo gì**:
  - Tạo chương trình "Mua 5 tặng 1" cho cafe
  - Voucher 20% cho KH VIP, expiry 7 ngày
  - Tier (Bronze/Silver/Gold) dựa trên doanh thu năm
  - Next order coupon: tự sinh coupon cho KH sau khi mua >500k
  - Loyalty card với barcode/QR — quét tích điểm tại POS
- **Module**: `loyalty`, `pos_loyalty`, `sale_loyalty`, `website_sale_loyalty`
- **Link**: https://odoo.com/app/loyalty

### 💎 **Subscriptions / Recurring billing** (EE) — Đăng ký hàng tháng
- **Demo gì**: KH mua gói SaaS 99$/tháng → tự động sinh invoice mỗi tháng qua Stripe → MRR dashboard
- **Use case**: SaaS, gym membership, bảo hiểm, magazine
- **Link**: https://odoo.com/app/subscriptions

### 📊 **Sales commission** (OCA, 156★) — Tính hoa hồng sales
- **Repo**: https://github.com/OCA/commission
- **Demo gì**: Agent A bán 100tr → 5% hoa hồng → tự sinh phiếu chi
- **Modules**: `sale_commission`, `purchase_commission`, `hr_commission`
- **Rule**: theo sản phẩm, theo KH, theo category, theo nhân viên

---

## 2) KHO & VẬN HÀNH — "wow" nhất

### 🏭 **DDMRP — Demand Driven MRP** (OCA, 106★) — Cách mạng supply chain
- **Repo**: https://github.com/OCA/ddmrp
- **Bản chất**: Phương pháp lập kế hoạch kho mới (thay MRP cổ điển) — dựa trên **buffer positions** thay vì forecast. Cùng triết lý với Theory of Constraints (Goldratt).
- **Demo gì**:
  - Xem Stock Buffer cho mỗi SKU: Green/Yellow/Red zone
  - ADU (Average Daily Usage) tự tính rolling 90 ngày
  - Decoupled lead time → reorder tự động
  - Adjustment factor khi mùa vụ
  - **Parts Flow Index Report** → đo "health" của buffer
- **So với MRP thường**: ít stockout hơn 30-50%, ít inventory hơn 20-40% (case study thực tế)

### 🏗️ **Shopfloor / WMS barcode** (OCA) — Worker dùng tablet quét barcode
- **Repos**: https://github.com/OCA/stock-logistics-shopfloor + `stock-logistics-barcode` (188★)
- **Demo gì**:
  - Worker mở tablet → chọn picking → hiện "Đi đến A-03-2, lấy SP X, scan barcode"
  - Hỗ trợ vertical lift, scale, label printer qua IoT Box
  - Cluster picking (gom nhiều picking → 1 worker đi 1 lượt)
  - Putaway strategy thông minh (gợi ý vị trí)
- **Module**: `shopfloor`, `shopfloor_packing`, `shopfloor_batch_picking`

### 🌍 **Geospatial / GIS** (OCA, 234★) — Bản đồ tương tác
- **Repo**: https://github.com/OCA/geospatial
- **Demo gì**:
  - Hiển thị KH trên **bản đồ Leaflet** (zoom, cluster, heatmap)
  - Vẽ vùng giao hàng (polygon) → check KH có thuộc vùng không
  - Route optimization giữa các điểm giao
  - Field service: gửi tech gần nhất
- **Tech**: Leaflet.js + PostGIS

### 📅 **Release channels** (OCA) — Quản lý dispatch theo wave
- **Repo**: https://github.com/OCA/stock-logistics-release-channel
- **Demo gì**: 
  - Chia picking theo "wave" (sáng 8h, chiều 14h, đêm 22h)
  - Mỗi wave có priority, capacity limit
  - Auto-release khi đủ số lượng picking

### 🏠 **Maintenance / IoT** (CE + EE) — Máy móc IoT giao tiếp Odoo
- **Modules**: `iot_base`, `iot_drivers`, `iot_box_image`, `maintenance`
- **Demo gì**:
  - Odoo **IoT Box** (Raspberry Pi chạy Linux) kết nối máy in nhãn, cân điện tử, scanner, Posiflex
  - Đặt lệnh sản xuất → máy in tự in work order
  - Sensor nhiệt độ kho lạnh → trigger alert nếu >8°C
  - Predictive maintenance: PM dựa trên giờ chạy máy

### 🚚 **Delivery carrier integrations** (CE + OCA, 135★) — Real-time tracking
- **Modules**: `delivery`, `delivery_mondialrelay`, + OCA `delivery-carrier` (135★)
- **Demo gì**:
  - Tạo shipment → chọn GHTK / VNPost / FedEx / DHL
  - In label, tracking number
  - Webhook cập nhật trạng thái real-time
  - **OCA modules**: GHTK, ViettelPost, Bưu điện, J&T, Shopee Express (Vietnam-specific)
- **Link**: https://odoo.com/app/inventory

### 🔁 **RMA — Return Merchandise Authorization** (OCA, 91★) — Quy trình đổi trả
- **Repo**: https://github.com/OCA/rma
- **Demo gì**: KH gửi mail "muốn trả" → sales tạo RMA → warehouse nhận hàng → refund/credit note → lên kho lại
- **Modules**: `rma`, `rma_sale`, `rma_account`, `rma_purchase`

### 📦 **DMS — Document Management** (OCA, 164★) — File server trong Odoo
- **Repo**: https://github.com/OCA/dms
- **Demo gì**:
  - Tree folder, drag-drop upload, version control
  - Lock file khi ai đó edit
  - Permission theo directory
  - Tag, search full-text, link document vào record
  - Classification tự động (hợp đồng / hóa đơn / biên bản)
- **EE tương đương**: `documents` (mạnh hơn: OCR, AI classify, sign)

---

## 3) KẾ TOÁN & TÀI CHÍNH — "wow" nhất

### 🧾 **E-Invoice Viettel (VN)** (CE 19) — Đã có sẵn!
- **Module**: `l10n_vn`, `l10n_vn_edi_viettel`, `l10n_vn_edi_viettel_pos`
- **Demo gì**:
  - Lập hóa đơn → đẩy lên Viettel S-Invoice → lấy mã CQT
  - Đồng bộ trạng thái (đã phát hành, đã hủy, đã thay thế)
  - Tự động sinh hóa đơn cho POS
- **Tiết kiệm**: 100-300k/tháng so với mua phần mềm hóa đơn riêng

### 🌍 **Peppol e-invoice** (CE 19) — Chuẩn quốc tế
- **Modules**: `account_peppol`, `account_peppol_advanced_fields`, `account_peppol_response`
- **Demo gì**:
  - Odoo trở thành Peppol **Access Point** (giống 1 nhà cung cấp dịch vụ)
  - Gửi/nhận e-invoice UBL giữa doanh nghiệp Châu Âu, Singapore, Úc
  - Lookup partner qua GLN/EAS
- **Use case**: SME EU bắt buộc dùng Peppol từ 2025

### 🤝 **Bank reconciliation + Bank statement import** (CE + OCA, 209★)
- **Module**: `account_bank_statement_import`, OCA `bank-statement-import` (209★)
- **Demo gì**:
  - Import file CSV/MT940/OFX/QIF từ Vietcombank/Techcombank → Odoo tự match với invoice
  - Auto-reconcile khi số tiền + reference khớp
  - Rule engine: "KH nào chuyển đúng 100k lẻ → auto match invoice 1234"
- **Repo**: https://github.com/OCA/bank-statement-import
- **Tiết kiệm**: 2-4 giờ/tháng kế toán

### 📑 **EDI — Electronic Data Interchange** (CE + OCA, 139★)
- **Module OCA**: https://github.com/OCA/edi
- **Demo gì**:
  - Nhận đơn hàng từ đối tác qua **EDI X12 / EDIFACT / UBL**
  - Tự động parse → tạo SO trong Odoo
  - Gửi ASN (Advance Ship Notice) khi xuất hàng
  - Trao đổi invoice PDF + XML tự động

### 💰 **SEPA QR + QR code EMV** (CE) — QR trên hóa đơn
- **Modules**: `account_qr_code_sepa` (châu Âu), `account_qr_code_emv` (châu Á)
- **Demo gì**: Mỗi invoice có QR chứa IBAN/amount/reference → KH quét app ngân hàng → trả

### 📊 **MIS Builder** (OCA, 176★) — KPI tự build
- **Repo**: https://github.com/OCA/mis-builder
- **Demo gì**:
  - Tạo P&L theo **account hierarchy** tùy ý (vd: gộp 644, 645, 646 thành "Chi phí vận hành")
  - Budget vs Actual, period comparison
  - Drill-down từ cell vào journal entry
  - Xuất Excel, print report, lên dashboard
- **So với Pivot Table Excel**: refresh tự động, multi-period, comparison

### 💎 **Multi-company / Multi-currency / Multi-language** (CE) — Multi-site
- **Modules**: `base`, `currency` (OCA, 80★)
- **Demo gì**:
  - Cty mẹ VN + cty con US, UK → 1 database, 3 currency, 3 tax regime
  - Auto revaluation cuối tháng
  - Crypto currency support (Bitcoin/Ethereum qua OCA/currency)
  - Inter-company transaction tự sinh SO/PO chéo

### 💳 **Credit control** (OCA, 104★) — Đòi nợ tự động
- **Repo**: https://github.com/OCA/credit-control
- **Demo gì**:
  - Level 0: nhắc 1 ngày trước due date
  - Level 1: gửi email 3 ngày sau
  - Level 2: gọi điện 7 ngày sau
  - Level 3: ngừng giao hàng
  - Tự động chạy cron hàng ngày
- **Tiết kiệm**: AR team 50-70% thời gian

---

## 4) SẢN XUẤT & VẬN HÀNH — "wow" nhất

### 🏭 **MRP — Manufacturing Resource Planning** (CE) — Full MES
- **Modules**: `mrp`, `mrp_subcontracting`, `mrp_subcontracting_dropshipping`, `mrp_repair`, `mrp_product_expiry`
- **Demo gì**:
  - BOM (Bill of Materials) đa cấp, routing (work centers)
  - Lệnh sản xuất → tự sinh PO cho NVL thiếu
  - Subcontracting: gửi NVL cho nhà thầu phụ → nhận thành phẩm
  - Dropshipping: KH đặt → mua từ NCC → ship thẳng KH
  - Landed costs: thêm phí customs/vận chuyển vào giá vốn
  - Repair: quy trình sửa chữa + warranty tracking
  - Product expiry: quản lý lô có hạn sử dụng
- **Link**: https://odoo.com/app/manufacturing

### ⏱️ **Quality control** (CE) — Checklist cho từng bước
- **Module**: `quality` (CE) + `quality_control_oca` (OCA)
- **Demo gì**:
  - Mỗi work order có QC checklist: "Nhiệt độ 80±2°C trong 10 phút"
  - QC fail → trigger NCR (Non-Conformance Report) → rework
  - Sampling: kiểm 5% lô ngẫu nhiên
  - SPI (Statistical Process Control) chart

### 🏥 **Field Service** (EE) — Kỹ thuật viên hiện trường
- **Demo gì**:
  - KH gọi "máy lạnh hỏng" → ticket → assign tech gần nhất (GIS)
  - Tech nhận task trên mobile → check-in GPS → làm → check-out
  - Spare parts request từ hiện trường
  - Customer signature trên tablet
  - Time tracking auto
- **Link**: https://odoo.com/app/field-service

### 📋 **PLM — Product Lifecycle Management** (EE)
- **Demo gì**: Version BOM, ECO (Engineering Change Order), approval workflow, document version control

### 🏨 **Vertical modules** (OCA)
- `vertical-medical` (291★) — Hồ sơ bệnh nhân, lịch hẹn, đơn thuốc, ICD-10
- `vertical-hotel` (154★) — Quản lý khách sạn
- `pms` (82★) — Property Management (Airbnb-style)
- `contract` (214★) — Subscription/contract management
- `commission` (156★) — Hoa hồng
- `maintenance` (105★) — Bảo trì thiết bị

---

## 5) NHÂN SỰ & DỰ ÁN — "wow" nhất

### ⏰ **Timesheet Grid** (CE/EE) — Bảng chấm công Excel-like
- **Modules**: `hr_timesheet`, `hr_timesheet_attendance`
- **Demo gì**:
  - Grid weekly view, kéo thả fill
  - Auto-fill từ attendance (check-in/out)
  - Validate overlap, holiday, sick day
  - Project → task → timesheet chain
  - Cost theo hourly_cost của nhân viên
  - OCA `timesheet` (161★) thêm: budget, deadline warning, sale order integration

### 🏖️ **HR Time-off (Holidays)** (CE + OCA 62★)
- **Modules**: `hr_holidays`, OCA `hr-holidays`
- **Demo gì**:
  - Employee xin nghỉ 3 ngày → manager duyệt → tự deduct quota
  - Mandatory days, accrued days, carry-over
  - Calendar view team-wide
  - OCA: `hr_holidays_public` — public holiday theo quốc gia
  - OCA: `hr_holidays_work_entry` — tích hợp payroll

### 📅 **Planning** (EE) — Shift schedule visual
- **Demo gì**:
  - Drag-drop shift cho 50 nhân viên / 4 tuần
  - Auto-balance workload
  - Color-code theo role
  - Publish → nhân viên nhận app mobile
  - Conflict detect: ai đang overlap với ca khác
- **Link**: https://odoo.com/app/planning

### 🎓 **eLearning / Slides** (CE) — LMS trong Odoo
- **Modules**: `website_slides`, `website_slides_forum`, `website_slides_survey`, `elearning`
- **Demo gì**:
  - Upload slide/PPT/PDF/video → Odoo stream + chapter
  - Quiz sau mỗi slide
  - Track progress, certificate
  - Comment + like (mạng xã hội)
  - Sell courses (gắn vào ecommerce)
- **Link**: https://odoo.com/app/elearning

### 📊 **Project + Task** (CE) — Kanban + Gantt + Calendar
- **Modules**: `project`, `project_task`, `project_timesheet`, `project_sale`
- **Demo gì**:
  - Task Kanban với drag-drop, swimlane (group by stage/assignee/priority)
  - Gantt view với dependency arrow, critical path
  - Timesheet từ task
  - Burndown chart
  - SO → project → invoice tự động
  - OCA `project` (393★): thêm 80+ module nâng cao

### 📈 **Spreadsheet + Dashboard** (CE 19) — Excel trong Odoo
- **Modules**: `spreadsheet`, `spreadsheet_dashboard_*` (hàng chục dashboard có sẵn)
- **Demo gì**:
  - Cell formula đầy đủ (=SUM, =VLOOKUP, =PIVOT)
  - Pivot table từ Odoo data
  - Chart (bar, line, pie, scatter)
  - Insert Odoo record vào cell (vd: `=ODOO.SALE("amount_total")`)
  - **Dashboard**: KPI tile + chart realtime, drill-down vào record
  - Template có sẵn: Sales dashboard, HR dashboard, POS dashboard, Livechat dashboard, Ecommerce dashboard
- **Khác biệt với Excel**: real-time, multi-user edit, embedded record link

### 📝 **Approvals** (EE) — Workflow duyệt đa cấp
- **Demo gì**:
  - SO > 100tr → cần 2 cấp duyệt (Manager + Director)
  - Expense > 5tr → cần Finance
  - Request → approve/reject với comment → notify
  - OCA: `base_tier_validation` (free, cũng tốt)
- **Link**: https://odoo.com/app/approvals

### 👥 **Recruitment (ATS)** (CE/EE) — Tracking ứng viên
- **Modules**: `hr_recruitment`, `hr_recruitment_skills`, `hr_recruitment_survey`, `hr_recruitment_sms`
- **Demo gì**:
  - Job posting lên website, LinkedIn, Indeed
  - Application tracking Kanban (Sourced/Screening/Interview/Offer/Hired)
  - Skill match score: tự động điểm CV theo kỹ năng yêu cầu
  - Survey trước phỏng vấn
  - SMS candidate
  - Hire → tự tạo employee

### 🏠 **Homeworking** (CE 19) — Quản lý remote
- **Modules**: `hr_homeworking`, `hr_homeworking_calendar`
- **Demo gì**:
  - Employee đăng ký "Thứ 2-3-4 work from home"
  - Manager duyệt → lên calendar team
  - Constraint: max 3 ngày/tuần
  - Tự sync với Google Calendar

### 🎯 **Skills management** (CE 19) — Cơ sở dữ liệu kỹ năng
- **Modules**: `hr_skills`, `hr_skills_event`, `hr_skills_slides`
- **Demo gì**:
  - Mỗi employee có skill tree (Python: 4/5, Public speaking: 3/5)
  - Tìm người có skill X với level ≥3 (cho dự án)
  - Auto-suggest slide/khóa học để improve gap
  - Gắn skill vào job position

---

## 6) MARKETING & CRM — "wow" nhất

### 📧 **Email Marketing** (CE) — Newsletter + drip campaign
- **Modules**: `mass_mailing`, `mass_mailing_sms`, `mass_mailing_crm`
- **Demo gì**:
  - WYSIWYG editor kéo-thả template
  - List segmentation (KH ở HN, mua >1tr, 6 tháng qua)
  - A/B test subject
  - Tracking open/click → push về CRM (mỗi click tạo activity)
  - Unsubscribe theo category (GDPR)

### 📲 **SMS Marketing** (CE 19) + Twilio gateway
- **Modules**: `sms`, `sms_twilio`, `mass_mailing_sms`
- **Demo gì**: gửi SMS cho KH không có email, track delivery

### 📅 **Events** (CE) — Tổ chức hội thảo
- **Modules**: `event`, `event_booth`, `event_sale`, `event_track`, `event_sms`, `event_crm`
- **Demo gì**:
  - Public event page (đẹp như Eventbrite)
  - Đăng ký + thanh toán online
  - Booth cho nhà tài trợ
  - Track (session) với speaker, slide, video
  - Live broadcast với quiz poll (`event_track_live_quiz`)
  - CRM tự sinh lead từ attendee

### 📋 **Survey / Form Builder** (CE) — Khảo sát đa năng
- **Modules**: `survey`, `survey_crm`, `hr_recruitment_survey`
- **Demo gì**:
  - Tạo form với 20+ loại câu hỏi (text, multiple choice, matrix, scale, file upload, signature)
  - Logic branching (câu 5 = A → skip 6-10)
  - Public link + embed
  - Auto-score, certificate sau khi pass
  - Use case: NPS, customer satisfaction, 360° review, quiz nội bộ

### 💬 **Live Chat** (CE) — Chat trực tiếp trên web
- **Modules**: `im_livechat`, `website_livechat`, `crm_livechat`, `hr_livechat`
- **Demo gì**:
  - Widget chat góc phải web → visitor gửi → agent nhận
  - Routing rule (chọn dept theo URL page)
  - Chat history vào CRM chatter
  - Rating sau chat
  - Chatbot rule: "Nếu hỏi giá → auto reply"

### 🗣️ **Forum / Blog** (CE) — CMS
- **Modules**: `website_forum`, `website_blog`, `website_slides_forum`
- **Demo gì**: Community forum kiểu StackOverflow, Karma system, moderation, tag

### 🤝 **Referral** (EE) — Giới thiệu KH mới
- **Module**: `hr_referral`
- **Demo gì**:
  - Employee giới thiệu ứng viên → tracking qua pipeline
  - Ứng viên hired → employee nhận thưởng
  - Public page cho candidate apply

### 📞 **VoIP** (CE/EE) — Gọi điện tích hợp
- **Demo gì**: Click phone icon trong CRM → Asterisk/FreePBX ring → ghi âm + ghi chú → activity log

### 📱 **WhatsApp Business** (EE) — Chat WA chính thức
- **Module**: `whatsapp`
- **Demo gì**: Nhận tin nhắn WA từ KH → trả lời trong Odoo chatter → template marketing

---

## 7) TÍCH HỢP & DEVELOPER — "wow" nhất

### 🔌 **Connector framework** (OCA, 370★) — Đa kênh
- **Repo**: https://github.com/OCA/connector
- **Demo gì**:
  - Magento ↔ Odoo (106★): product, stock, order 2 chiều
  - Prestashop ↔ Odoo (93★)
  - Amazon, eBay, Shopify
  - Salesforce, SugarCRM
  - **Backend**: queue job (chạy async, retry, chunked)

### 📦 **OpenUpgrade** (OCA, 952★) — Nâng cấp CE qua version
- **Repo**: https://github.com/OCA/OpenUpgrade
- **Bản chất**: Migration tool cho CE (Enterprise có migration chính thức, CE phải tự migrate)
- **Demo gì**: Odoo 16 → 17 → 18 → 19 với data thật

### 🔐 **Auth: Passkey, OAuth, 2FA, LDAP** (CE 19) — Security mới nhất
- **Modules**:
  - `auth_passkey` / `auth_passkey_portal` — Passkey (FIDO2/WebAuthn, không cần password)
  - `auth_oauth` — Google/Microsoft/Facebook login
  - `auth_totp` / `auth_totp_portal` / `auth_totp_mail` — 2FA
  - `auth_ldap` — LDAP/Active Directory
  - `auth_password_policy` / `auth_signup` — password rules
  - `auth_timeout` — auto logout
  - `iap` — In-App Purchase (gateway Odoo)
- **Demo gì**: Login bằng vân tay (Touch ID / Windows Hello), không cần gõ password

### 🗺️ **Web hierarchy view** (CE 19) — Org chart visual
- **Module**: `web_hierarchy`
- **Demo gì**: Drag-drop sơ đồ tổ chức (CEO → VP → Manager → Staff), live preview

### 🗑️ **Data recycle** (CE 19) — GDPR auto-cleanup
- **Module**: `data_recycle`
- **Demo gì**: 
  - Quy tắc: "Lead không có activity > 6 tháng → ẩn"
  - "Hóa đơn > 10 năm → xóa PDF"
  - Cron chạy hàng ngày → preview trước khi xóa

### 📡 **IoT Box** (CE) — Pi box kết nối thiết bị
- **Modules**: `iot_base`, `iot_drivers`, `iot_box_image`
- **Demo gì**: Raspberry Pi cài Odoo IoT image → kết nối scale, printer, scanner → hiển thị trong Odoo Settings

### 📊 **MIS Builder** (OCA, 176★) — Reporting linh hoạt
- **Repo**: https://github.com/OCA/mis-builder
- **Demo gì**: Tự build report tổng hợp doanh thu theo bất kỳ hierarchy/account dimension, kéo thả

### 🖨️ **Print node / Label printer** (CE + OCA, 136★) — In từ IoT
- **Repo**: https://github.com/OCA/report-print-send
- **Demo gì**: In tem mã vạch từ POS → máy in Zebra qua IoT Box (không cần driver Windows)

---

## TOP 10 TÍNH NĂNG DEMO GÂY "WOW" NHẤT

Nếu chỉ có 30 phút demo, đây là 10 thứ khiến khách há hốc mồm:

| # | Tính năng | Link | Phụ thuộc |
|---|---|---|---|
| 1 | **Spreadsheet Dashboard** real-time KPI | https://odoo.com/app/spreadsheet | CE 19 (đã có) |
| 2 | **POS Self-Order QR** (khách tự order) | https://odoo.com/app/point-of-sale | CE |
| 3 | **Loyalty / Coupon engine** (kiểu Starbucks) | https://odoo.com/app/loyalty | CE |
| 4 | **Geospatial Leaflet map** (KH trên bản đồ) | https://github.com/OCA/geospatial | CE + OCA |
| 5 | **Manufacturing MRP + Subcontracting** | https://odoo.com/app/manufacturing | CE |
| 6 | **DDMRP buffer** (game-changer supply chain) | https://github.com/OCA/ddmrp | CE + OCA |
| 7 | **E-Invoice Viettel** (real VN, tiết kiệm $$$) | `l10n_vn_edi_viettel` | CE 19 (đã có) |
| 8 | **Bank statement auto-reconcile** | OCA `bank-statement-import` | CE + OCA |
| 9 | **Multi-currency + Crypto** (Bitcoin accepted) | OCA `currency` | CE + OCA |
| 10 | **Event + Live broadcast** (zoom-like) | https://odoo.com/app/events | CE |

Nếu có EE license, thay thế bằng:

| # | Tính năng EE | Link |
|---|---|---|
| A | **Field Service** (tech GPS + signature) | https://odoo.com/app/field-service |
| B | **Documents OCR AI** (scan hóa đơn tự nhập) | https://odoo.com/app/documents |
| C | **Approvals** (multi-tier) | https://odoo.com/app/approvals |
| D | **Sign** (e-signature workflow) | https://odoo.com/app/sign |
| E | **Subscriptions** (recurring billing) | https://odoo.com/app/subscriptions |

---

## Tất cả link (quick ref)

### OCA theo stars (top 30)
- OCA/web — 1189★ UI addons: https://github.com/OCA/web
- OCA/OpenUpgrade — 952★ upgrade tool: https://github.com/OCA/OpenUpgrade
- OCA/server-tools — 898★ admin tools: https://github.com/OCA/server-tools
- OCA/reporting-engine — 418★ alternative QWeb: https://github.com/OCA/reporting-engine
- OCA/account-financial-tools — 409★ accounting: https://github.com/OCA/account-financial-tools
- OCA/stock-logistics-warehouse — 395★ WMS core: https://github.com/OCA/stock-logistics-warehouse
- OCA/sale-workflow — 394★ sales: https://github.com/OCA/sale-workflow
- OCA/project — 393★ project: https://github.com/OCA/project
- OCA/connector — 370★ integrations: https://github.com/OCA/connector
- OCA/OCB — 368★ Odoo Community Backports: https://github.com/OCA/OCB
- OCA/pos — 339★ POS: https://github.com/OCA/pos
- OCA/website — 295★ website: https://github.com/OCA/website
- OCA/account-invoicing — 294★ invoicing: https://github.com/OCA/account-invoicing
- OCA/vertical-medical — 291★ hospital: https://github.com/OCA/vertical-medical
- OCA/stock-logistics-workflow — 288★ warehouse: https://github.com/OCA/stock-logistics-workflow
- OCA/purchase-workflow — 283★ purchasing: https://github.com/OCA/purchase-workflow
- OCA/hr — 272★ HR: https://github.com/OCA/hr
- OCA/queue — 256★ async jobs: https://github.com/OCA/queue
- OCA/manufacture — 252★ MRP: https://github.com/OCA/manufacture
- OCA/knowledge — 242★ DMS: https://github.com/OCA/knowledge
- OCA/product-attribute — 238★ product variant: https://github.com/OCA/product-attribute
- OCA/helpdesk — 234★ helpdesk: https://github.com/OCA/helpdesk
- OCA/geospatial — 234★ GIS: https://github.com/OCA/geospatial
- OCA/management-system — 227★ ISO: https://github.com/OCA/management-system
- OCA/crm — 223★ CRM: https://github.com/OCA/crm
- OCA/contract — 214★ contracts: https://github.com/OCA/contract
- OCA/wms — 210★ full WMS bundle: https://github.com/OCA/wms
- OCA/bank-statement-import — 209★ bank: https://github.com/OCA/bank-statement-import
- OCA/server-ux — 205★ UX: https://github.com/OCA/server-ux
- OCA/e-commerce — 193★ ecommerce: https://github.com/OCA/e-commerce
- OCA/stock-logistics-barcode — 188★ barcode: https://github.com/OCA/stock-logistics-barcode
- OCA/field-service — 183★ FSM: https://github.com/OCA/field-service
- OCA/mis-builder — 176★ KPI: https://github.com/OCA/mis-builder
- OCA/dms — 164★ document mgmt: https://github.com/OCA/dms
- OCA/timesheet — 161★ timesheet: https://github.com/OCA/timesheet
- OCA/commission — 156★ commission: https://github.com/OCA/commission
- OCA/vertical-hotel — 154★ hotel: https://github.com/OCA/vertical-hotel
- OCA/edi — 139★ EDI: https://github.com/OCA/edi
- OCA/delivery-carrier — 135★ shipping: https://github.com/OCA/delivery-carrier
- OCA/multi-company — 135★ multi-co: https://github.com/OCA/multi-company
- OCA/payroll — 117★ payroll: https://github.com/OCA/payroll
- OCA/rma — 91★ returns: https://github.com/OCA/rma
- OCA/ddmrp — 106★ DDMRP: https://github.com/OCA/ddmrp
- OCA/maintenance — 105★ maintenance: https://github.com/OCA/maintenance
- OCA/credit-control — 104★ dunning: https://github.com/OCA/credit-control
- OCA/currency — 80★ crypto/multi-currency: https://github.com/OCA/currency
- OCA/pms — 82★ property mgmt: https://github.com/OCA/pms
- OCA/operating-unit — 95★ BU: https://github.com/OCA/operating-unit

### Odoo official apps
- Odoo 19 release notes: https://www.odoo.com/page/odoo-19
- Apps store (all modules): https://apps.odoo.com
- All EE apps: https://www.odoo.com/page/all-apps
- Spreadsheet: https://odoo.com/app/spreadsheet
- Sign: https://odoo.com/app/sign
- Documents: https://odoo.com/app/documents
- Field Service: https://odoo.com/app/field-service
- Planning: https://odoo.com/app/planning
- Helpdesk: https://odoo.com/app/helpdesk
- Subscriptions: https://odoo.com/app/subscriptions
- Approvals: https://odoo.com/app/approvals
- Knowledge: https://odoo.com/app/knowledge
- Manufacturing: https://odoo.com/app/manufacturing
- POS: https://odoo.com/app/point-of-sale
- Loyalty: https://odoo.com/app/loyalty
- Events: https://odoo.com/app/events
- eLearning: https://odoo.com/app/elearning
- Inventory: https://odoo.com/app/inventory

### Tài liệu hay
- Odoo eLearning (miễn phí): https://odoo.com/slides
- Odoo Forum: https://odoo.com/forum
- OCA docs: https://odoo-community.org/

---

File: `/home/khoa/Company/odoo/ODOO_DEMO_FEATURES.md` (≈17KB)
