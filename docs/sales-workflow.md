# Workflow Bán Hàng Odoo 18.0

Tài liệu giải thích toàn bộ quy trình bán hàng, từ khách vào website → đặt hàng → thanh toán → xuất kho → hóa đơn → kế toán.

---

## Tổng quan các module liên quan

| Module | Chức năng |
|---|---|
| `website_sale` | Cửa hàng online, giỏ hàng, checkout |
| `website_sale_payment` | Tích hợp payment provider (Stripe, PayPal, v.v.) |
| `sale` (`sale.order`, `sale.order.line`) | Đơn bán hàng nội bộ (B2B) |
| `sale_management` | Workflow nâng cao cho sale.order (discount, variant) |
| `stock` (`stock.picking`) | Xuất/nhập kho |
| `account` (`account.move`) | Hóa đơn, thanh toán, sổ cái |
| `purchase` (`purchase.order`) | Đơn mua hàng (nhập hàng từ NCC) |
| `crm` (optional) | Lead/Opportunity trước khi thành khách hàng |

**Trạng thái hiện tại trong dự án:** đã cài `website_sale`, `sale`, `sale_management`, `stock`, `account`, `purchase`, `account_accountant`, `mass_mailing`, `l10n_vn`.

---

## 1. Quy trình tổng thể (B2C — bán lẻ online)

```
Khách truy cập website
       │
       ▼
[Xem sản phẩm, danh mục]        ← website_sale
       │
       ▼
[Thêm vào giỏ hàng]              ← website_sale
       │
       ▼
[Checkout: nhập địa chỉ, chọn shipping]   ← website_sale
       │
       ▼
[Chọn payment method]
   ├── Online (Stripe/PayPal)  ──► Payment Transaction ──► Capture
   ├── COD (Cash on Delivery)  ──► Order confirmed, payment = pending
   └── Bank transfer          ──► Manual reconciliation
       │
       ▼
[Order confirmed]                ← sale.order state: 'sale'
       │
       ▼
[Xuất kho / Delivery]            ← stock.picking
   ├── Delivery Order
   ├── Pack
   └── Validate (trừ tồn kho)
       │
       ▼
[Hóa đơn / Invoice]              ← account.move (out_invoice)
   ├── Draft (nháp)
   ├── Confirmed (đã xác nhận)
   └── Posted (đã ghi sổ)
       │
       ▼
[Thanh toán / Payment]           ← account.payment
   └── Register payment → reconcile với invoice
       │
       ▼
[Done — Kế toán ghi nhận doanh thu]
```

---

## 2. Khách hàng & Đối tượng

### 2.1 Ba cấp độ khách hàng trong Odoo

| Cấp | Model | Khi nào dùng |
|---|---|---|
| **Visitor** | (không tạo record) | Người lạ xem website, chưa mua |
| **Public user** | `res.partner` (với `is_public=True`) | Khách đã đăng ký tài khoản portal |
| **Contact / Customer** | `res.partner` (với `customer_rank > 0`) | Khách đã mua hoặc được tạo thủ công |

### 2.2 Quản lý khách hàng (CRM)

**Đường dẫn UI:** `CRM > Customers` hoặc `Contacts > Contacts`

**Cách tạo khách hàng:**

**Cách 1: Thủ công**
```bash
# Qua UI
Contacts → New → điền Name, Email, Phone, Address → Save
```
**Cách 2: Khi checkout website** — tự động
- Khách điền thông tin checkout → Odoo tự tạo `res.partner` (loại `contact` hoặc `delivery` hoặc `invoice` address)

**Cách 3: Import CSV**
```bash
# Qua UI
Contacts → Favorites (⭐) → Import Records → upload CSV
# Columns tối thiểu: name, email, phone, street, city, country_id/id
```

**Cách 4: Qua CLI**
```bash
bash scripts/cli.sh shell -d odoo_dev
# Trong shell:
partner = env['res.partner'].create({
    'name': 'Nguyen Van A',
    'email': 'a@example.com',
    'phone': '+84912345678',
    'street': '123 Le Loi',
    'city': 'Ho Chi Minh',
    'country_id': env.ref('base.vn').id,
})
env.cr.commit()
```

**Cách 5: Khi có Lead/Opportunity thắng (CRM)**
- Module `crm`: tạo Lead → Qualify → chuyển thành Opportunity → thắng → tự sinh Customer

### 2.3 Phân loại khách hàng

- **Individual** (cá nhân): `is_company = False`
- **Company** (doanh nghiệp): `is_company = True`, có thể có nhiều `child_ids` (contacts của công ty)
- **VIP/Tag**: dùng `category_id` (tags) để phân nhóm (vd: "VIP", "Wholesale")

### 2.4 Địa chỉ giao hàng vs hóa đơn

Một `res.partner` có thể có:
- `type='contact'` — địa chỉ chính
- `type='delivery'` — địa chỉ giao hàng
- `type='invoice'` — địa chỉ xuất hóa đơn

Khi checkout, khách nhập 3 địa chỉ khác nhau → Odoo tạo 1 company + 2 child partners.

---

## 3. Quy trình B2C — Bán lẻ qua website

### Bước 1: Khách vào website

```
http://localhost:8069/shop
```
- Website hiển thị sản phẩm published (`website_published=True`)
- Filter theo category, search theo tên
- Click vào sản phẩm → chi tiết, chọn variant (size, color), số lượng

### Bước 2: Thêm vào giỏ

```
Click "Add to Cart" → /shop/cart
```
- Odoo tạo `sale.order` với `state='draft'`, line items
- Lưu vào session (cookie) hoặc `res.partner` nếu đã login
- Giỏ hàng cập nhật real-time

### Bước 3: Checkout

```
/shop/checkout
```

Khách điền:
1. **Contact info:** email, phone
2. **Delivery address:** street, city, country
3. **Invoice address:** (mặc định = delivery, có thể khác)
4. **Shipping method:** `delivery.carrier` (vd: Standard, Express)
5. **Payment method:** `payment.provider` (Online/COD/Bank transfer)

Khi click "Pay now" hoặc "Place order":
- Odoo tạo `sale.order` với `state='sale'` (confirmed)
- Tạo `account.move` (invoice) nếu payment immediate
- Tạo `stock.picking` (delivery order) nếu sản phẩm cần ship
- Tạo `payment.transaction`

### Bước 4: Thanh toán

**4.1 Online payment (Stripe/PayPal)**

```
[Stripe] → form nhập card → Stripe charge → webhook → 
   payment.transaction state='done' → 
   account.payment registered → 
   account.move.state='posted' (auto-posted)
```

**Setup Stripe:**
1. Lấy API key từ https://dashboard.stripe.com/apikeys
2. Trong Odoo: `Website > Configuration > Payment Providers > Stripe`
3. Dán `Publishable Key` + `Secret Key`
4. Chọn currencies: VND/USD
5. Enable

**4.2 COD (Cash on Delivery)**
- Order confirmed
- Invoice = draft
- Khi giao hàng, nhân viên thu tiền mặt → register payment manually trong backend

**4.3 Bank transfer (VN)**
- Hiển thị số tài khoản ngân hàng VN (config trong payment provider)
- Khách chuyển khoản → Odoo chờ `payment.transaction` manual confirm
- Kế toán check sao kê → reconcile

### Bước 5: Xử lý đơn (Backend)

**Đường dẫn:** `Sales > Orders > Quotations`

```
Sale Order: SO001
  - state='sale' (confirmed)
  - Picking: WH/OUT/0001 (waiting)
  - Invoice: INV/2026/0001 (draft)
```

Nhân viên sale:
1. Vào Sale Order → kiểm tra thông tin
2. Nếu cần sửa: click "Edit" (chỉ khi chưa invoice)
3. Click "Confirm" (nếu chưa)

Nhân viên kho (`Inventory`):
1. `Inventory > Delivery Orders`
2. Mở `WH/OUT/0001`
3. Click "Check availability" → Odoo reserve stock
4. Click "Validate" → trừ tồn kho, set state='done'

Kế toán (`Accounting`):
1. `Accounting > Invoices`
2. Mở `INV/2026/0001`
3. Click "Confirm" (nếu draft)
4. Click "Register payment" → nhập amount, journal (bank/cash)
5. Payment reconciled → invoice state='paid'

### Bước 6: Done

- Tồn kho giảm
- Doanh thu ghi nhận (`account.move.line` credit revenue account)
- Tiền vào bank/cash (`account.move.line` debit bank)
- Hoàn tất.

---

## 4. Quy trình B2B — Bán sỉ / bán qua đơn hàng nội bộ

Khác B2C: khách không mua qua web, mà nhân viên sale tạo quote/so thủ công.

### Bước 1: Tạo khách hàng (B2B company)

```
Contacts → New
  - Name: "Công ty ABC"
  - Is Company: ✓
  - Tax ID: "0123456789" (VN MST)
  - Country: Vietnam
  - Currency: VND
  - Customer Rank: 1
  - Tags: "Wholesale", "VIP"
```

### Bước 2: Tạo báo giá (Quotation)

```
Sales → Quotations → New
  - Customer: Công ty ABC
  - Order Lines:
      [+] Product A, Qty 100, Unit Price 50,000
      [+] Product B, Qty 50,  Unit Price 120,000
  - Payment Terms: 30 ngày (net 30)
  - Validity: 14 ngày
  - Click "Send by Email" → khách nhận PDF
  - state = 'draft' (quotation)
```

### Bước 3: Khách duyệt / ký

Có 2 cách:
- **Online:** Khách click "Sign & Pay" trong email → state='sale' (nếu dùng `sign` + payment)
- **Manual:** Sale staff click "Confirm" sau khi nhận xác nhận qua điện thoại/email

### Bước 4: Delivery + Invoice

Giống B2C bước 5-6.

### Bước 5: Thanh toán sau (B2B thường dùng)

B2B thường có **payment term** (vd: Net 30 = thanh toán trong 30 ngày):

```
Sale Order confirmed
   ↓
Invoice created (state='posted', chưa paid)
   ↓
Khách thanh toán trong 30 ngày
   ↓
Kế toán: Accounting > Invoices > INV/... > Register Payment
   ↓
Invoice state='paid'
```

---

## 5. Quy trình Mua hàng (Purchase)

Để có hàng bán, phải mua từ NCC. Quy trình song song với bán hàng.

### Bước 1: Tạo NCC (Vendor)

```
Contacts → New
  - Name: "Nhà cung cấp XYZ"
  - Is Company: ✓
  - Is Vendor: ✓ (Vendor Rank = 1)
```

### Bước 2: Tạo đơn mua

```
Purchase → Orders → New (RFQ)
  - Vendor: NCC XYZ
  - Order Lines:
      [+] Product A, Qty 500, Unit Price 30,000
  - Click "Confirm Order" → state = 'purchase'
```

### Bước 3: Nhận hàng

```
Inventory → Receipts
  - WH/IN/0001
  - Click "Validate" → tăng tồn kho
```

### Bước 4: Hóa đơn mua (Vendor Bill)

```
Accounting > Vendor Bills > New
  - Vendor: NCC XYZ
  - Invoice Lines: Product A, Qty 500, Price 30,000
  - Confirm → state='posted'
  - Register Payment → paid
```

---

## 6. Hóa đơn & Thanh toán (Accounting)

### 6.1 Phân biệt

| Khái niệm | Odoo model | Mục đích |
|---|---|---|
| **Hóa đơn** (Invoice) | `account.move` (type=out_invoice/in_invoice) | Yêu cầu thanh toán |
| **Thanh toán** (Payment) | `account.payment` | Ghi nhận tiền vào/ra |
| **Sổ cái** (Journal Entry) | `account.move` (type=entry) | Bút toán kế toán thuần |
| **Báo có** (Credit Note) | `account.move` (type=out_refund) | Hoàn tiền / trả hàng |

### 6.2 Vòng đời hóa đơn

```
draft → posted → paid
         ↓
       cancel
```

- **draft:** nháp, có thể sửa
- **posted:** đã ghi sổ, có số hóa đơn (`INV/2026/0001`)
- **paid:** đã thanh toán đủ
- **cancel:** hủy (chỉ trước khi ghi sổ)

### 6.3 Thanh toán hóa đơn

**Cách 1: Register payment trực tiếp trên invoice**

```
Accounting > Invoices > INV/... > Register Payment
  - Journal: Bank (VNĐ) / Cash
  - Amount: 15,000,000
  - Date: 2026-06-05
  - Click "Create Payment"
  → state='paid', reconcile xong
```

**Cách 2: Match với bank statement**

```
Accounting > Bank > Bank Statements > Import
  → Odoo tự match payment với invoice (theo amount + partner)
```

### 6.4 Payment Terms (điều khoản thanh toán)

- `Immediate` — thanh toán ngay
- `Net 15` — 15 ngày
- `Net 30` — 30 ngày
- `50% upfront, 50% on delivery` — chia đợt
- Custom: `account.payment.term.line` (sequence, days, percent)

---

## 7. POS vs E-commerce vs Sale Order

| Đặc điểm | E-commerce | Sale Order | POS (Point of Sale) |
|---|---|---|---|
| Channel | Online | Manual/Internal | Tại quầy |
| Order | `sale.order` (`website_id` set) | `sale.order` | `pos.order` |
| Payment | Online provider / COD | Wire / Cheque / Cash | Tiền mặt tại quầy |
| Invoice | Tự động khi cần | Tự động hoặc manual | Tự động |
| Module | `website_sale` | `sale`, `sale_management` | `point_of_sale` |

Tất cả 3 channel đều tạo `account.move` (invoice) cuối cùng → tất cả vào sổ cái.

---

## 8. Workflow theo actor

### Sales (nhân viên bán hàng)

```
Hàng ngày:
  1. Sales > Orders > Quotations (filter: My)
  2. Mở quotation → Review → Send to customer / Confirm
  3. Sales > Orders > Orders (filter: Confirmed) → Check trạng thái
  4. Nếu khách yêu cầu: Click "Edit" (trước invoice) / "Cancel"
  5. Sales > Products → Check tồn kho, giá
```

### Warehouse (nhân viên kho)

```
Hàng ngày:
  1. Inventory > Overview → Check cảnh báo tồn kho
  2. Inventory > Delivery Orders > WH/OUT/000X
  3. Check availability → Pack → Validate
  4. Inventory > Receipts > WH/IN/000X (từ NCC) → Validate
  5. Inventory > Transfers > Internal moves (chuyển kho)
```

### Accounting (kế toán)

```
Hàng ngày:
  1. Accounting > Invoices > Customer Invoices → Confirm drafts
  2. Register payment khi nhận tiền
  3. Accounting > Vendor Bills → Confirm + schedule payment
  4. Accounting > Bank > Reconcile statements
  5. Accounting > Reporting > P&L, Balance Sheet, Cash Flow
```

### Customer (khách hàng)

```
Trên website:
  1. Browse shop /search
  2. Add to cart → Checkout
  3. Nhập thông tin → Chọn payment
  4. Nhận email xác nhận
  5. /shop/cart → track order status
  6. Portal: /my/orders → xem lịch sử, invoice
```

---

## 9. State machine quan trọng

### Sale Order (`sale.order`)

```
draft (Quotation)
  ↓ confirm
sale (Confirmed Sale Order)
  ↓ (optional) lock
done (Locked — không edit được)
  ↓ cancel
cancel (Cancelled)
```

### Stock Picking (`stock.picking`)

```
draft
  ↓ confirm
waiting (chờ available)
  ↓ check_availability
assigned (đã reserve)
  ↓ validate
done (đã xuất kho)
  ↓ cancel
cancel
```

### Account Move (`account.move`)

```
draft
  ↓ post
posted (đã ghi sổ)
  ↓ register_payment
paid (đã thanh toán)
  ↓
[posted] → reverse → refund (credit note)
```

### Payment Transaction (`payment.transaction`)

```
draft
  ↓ redirect_to_provider
pending
  ↓ provider_callback (success)
done (captured)
  ↓
error (failed)
cancel
```

---

## 10. Cấu hình cần thiết (một lần)

### 10.1 E-commerce (B2C)

```
Settings > Website
  - Shop page: /shop
  - Terms & Conditions: bật
  - Privacy: bật

Sales > Configuration > Payment Providers
  - Stripe: paste API key, enable
  - Manual: enable (cho bank transfer / COD)
  - Currency: VND

Inventory > Configuration > Warehouses
  - WH (main): default

Sales > Configuration > Delivery Methods
  - Standard Delivery: product = "Delivery", based_on = "price"
  - Express: based_on = "weight"
```

### 10.2 Accounting (VN)

```
Settings > Accounting
  - Default company: Your Company
  - Currency: VND
  - Fiscal year: 1/1 → 12/31

Accounting > Configuration > Journals
  - Bank (VND): tài khoản ngân hàng
  - Cash (VND): tiền mặt
  - Sales (VND): doanh thu
  - Purchase (VND): chi phí

Accounting > Configuration > Taxes (l10n_vn đã setup sẵn)
  - VAT 0%, 5%, 8%, 10%
  - Sales Tax, Purchase Tax
```

### 10.3 Payment providers (VN thường dùng)

| Provider | Loại | Setup |
|---|---|---|
| **Stripe** | Quốc tế | API keys từ dashboard |
| **PayPal** | Quốc tế | API credentials |
| **VNPay** | VN | Gateway e-commerce VN |
| **Momo** | VN | Ví điện tử |
| **Bank transfer** | Thủ công | Hiển thị số TK |
| **COD** | Manual | Tự enable |

---

## 11. Các tình huống thường gặp

### 11.1 Khách đặt hàng nhưng chưa thanh toán

```
Sale Order: state='sale' (đã confirm)
Payment Transaction: state='pending'
Invoice: state='posted' (chưa paid)
```

**Fix:** Gửi email nhắc nhở, hoặc cancel order nếu quá hạn.

### 11.2 Khách trả hàng

```
Sales > Orders > SO... > Return
  → Tạo delivery return (nhập lại kho)
Accounting > Credit Notes > New
  → Reverse invoice gốc
```

### 11.3 Hết hàng

```
Inventory > Replenishment
  → Tự động tạo Purchase Order cho NCC
Purchase > Orders > Confirm
```

### 11.4 Khách yêu cầu sửa đơn sau khi confirm

- Nếu **chưa invoice:** Sale staff click "Edit" → sửa → re-confirm
- Nếu **đã invoice:** Cancel invoice → edit order → re-invoice (hoặc tạo credit note + new order)

### 11.5 Đối soát thanh toán

```
Accounting > Bank > Bank Statements > Import CSV từ ngân hàng
  → Odoo suggest match với invoice (cùng amount + partner)
  → Click "Reconcile"
```

---

## 12. Báo cáo cần biết

| Báo cáo | Đường dẫn | Mục đích |
|---|---|---|
| Sales Orders | `Sales > Reporting > Sales` | Doanh thu theo tháng/sản phẩm |
| Invoices | `Accounting > Reporting > Invoices` | Tổng hợp hóa đơn |
| Aged Receivable | `Accounting > Reporting > Aged Receivable` | Khách nợ bao nhiêu ngày |
| Aged Payable | `Accounting > Reporting > Aged Payable` | Bạn nợ NCC bao nhiêu |
| Inventory Valuation | `Inventory > Reporting > Inventory Valuation` | Giá trị tồn kho |
| P&L | `Accounting > Reporting > Profit & Loss` | Lãi lỗ |
| Balance Sheet | `Accounting > Reporting > Balance Sheet` | Tài sản - Nợ |
| Cash Flow | `Accounting > Reporting > Cash Flow` | Dòng tiền |

---

## 13. Tích hợp với custom module

Module `hello_shop` hiện tại chỉ thêm 1 field demo. Khi mở rộng:

**Ví dụ: thêm workflow B2B với giá wholesale**

```python
# models/hello_product.py
class ProductTemplate(models.Model):
    _inherit = 'product.template'

    hello_tag = fields.Char(...)

    # B2B wholesale price
    wholesale_price = fields.Float(
        string='Wholesale Price',
        help='Price for B2B customers (Wholesale tag)',
    )

# sale_order.py
class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _get_pricelist(self):
        if self.partner_id.category_id.filtered(lambda c: c.name == 'Wholesale'):
            return self.env.ref('product.pricelist_wholesale')
        return super()._get_pricelist()
```

**Tham khảo OCA modules:**
- `sale_workflow` — discount, force invoicing
- `sale_order_product_recommendation` — gợi ý sản phẩm
- `website_sale_*` (e-commerce) — nhiều extension

---

## 14. Nơi tham chiếu trong code

| File chứa logic | Đường dẫn trong container |
|---|---|
| Sale order workflow | `/opt/odoo/addons/sale/models/sale_order.py` |
| E-commerce controllers | `/opt/odoo/addons/website_sale/controllers/main.py` |
| Payment transactions | `/opt/odoo/addons/payment/models/payment_transaction.py` |
| Account move (invoice) | `/opt/odoo/addons/account/models/account_move.py` |
| Stock picking | `/opt/odoo/addons/stock/models/stock_picking.py` |
| OCA sale-workflow | `/mnt/extra-addons/oca/sale-workflow/` |

Để đọc code Odoo core trong container:
```bash
docker compose exec odoo bash
cat /opt/odoo/addons/sale/models/sale_order.py | head -100
```

---

## Tóm tắt 1 phút

- **Khách hàng:** `res.partner`, tạo qua UI/CSV/CRM/checkout web
- **Bán hàng online:** website → cart → checkout → payment → delivery → invoice
- **Bán B2B:** Sale staff tạo quotation → confirm → delivery → invoice (Net 30)
- **Hóa đơn:** `account.move` (draft → posted → paid)
- **Thanh toán:** Register payment trên invoice, hoặc match bank statement
- **Kho:** `stock.picking` (waiting → assigned → done)
- **Mua hàng:** Vendor → PO → Receipt → Vendor Bill → Payment
