# Import E-commerce Team

Thứ tự import: **users → crm_team → crm_team_member** (vì team FK tới user, member FK tới cả 2).

## Bước 1: Users

1. **Settings → Users & Companies → Users**
2. Click **Favorites** (icon ⭐ ở góc phải) → **Import** (hoặc **Action → Import**)
3. Upload file `users_ecommerce_team.csv`
4. Click **Test** → xem kết quả → **Import**

Password mặc định sẽ random — user phải reset pass lần đầu login (gửi invite).

## Bước 2: CRM Teams

1. **Sales → Configuration → Sales Teams**
2. **Action → Import** (hoặc từ ⚙️ menu)
3. Upload `crm_team_ecommerce.csv`
4. Cột `user_id/login` resolve từ user đã tạo ở bước 1

## Bước 3: Team Members

1. Mở 1 team → tab **Members** → **Import** (cần vào list view)
2. Upload `crm_team_member_ecommerce.csv`

## Mapping tóm tắt

| User | Role | Team |
|---|---|---|
| ecom.admin@gmail.com | Ecom Admin (full) | – |
| ecom.lead@gmail.com | Sales Manager | Online Sales (lead) |
| ecom.sales1@gmail.com | Sales rep (all leads) | Online Sales + Marketplace |
| ecom.sales2@gmail.com | Sales rep (all leads) | B2B Direct |
| ecom.whmanager@gmail.com | Stock Manager | – |
| ecom.whstaff@gmail.com | Stock User | – |
| ecom.accountant@gmail.com | Accountant (invoice) | – |
| ecom.buyer@gmail.com | Purchase User | – |
| ecom.marketing@gmail.com | Mass Mailing | – |
| ecom.cskh@gmail.com | Helpdesk User | Customer Support |

## 4 Teams ecommerce

| Team | Channel | Target/tháng |
|---|---|---|
| Online Sales | Website | 500,000 |
| Marketplace | Amazon/eBay (mock) | 300,000 |
| B2B Direct | Outbound/calls | 800,000 |
| Customer Support | Post-sale | 0 |

## Lưu ý

- File dùng External ID prefix `__import__` (Odoo sẽ rewrite khi import; click "Replace" hoặc để trống nếu re-import).
- Nếu user đã tồn tại → skip dòng đó (không lỗi).
- Password rỗng: user phải dùng **Forgot Password** hoặc admin **Action → Send Password Reset**.
