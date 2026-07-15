# 🚕 Taxi Bot — Telegram Backend

**aiogram 3.x + PostgreSQL + SQLAlchemy (async) + Railway.app**

---

## 📁 Loyiha tuzilmasi

```
taxibot/
├── main.py                  # Asosiy kirish nuqtasi
├── config.py                # .env o'zgaruvchilarini o'qish
├── requirements.txt
├── Dockerfile
├── .env.example             # Namuna .env fayl
│
├── database/
│   ├── models.py            # SQLAlchemy ORM modellari
│   ├── engine.py            # Async engine va session factory
│   └── queries.py           # Barcha DB so'rovlari (CRUD + atomic tx)
│
├── handlers/
│   ├── common.py            # /start, bosh menyu
│   ├── driver.py            # Haydovchi ro'yxati, balans, buyurtma olish
│   ├── passenger.py         # Yo'lovchi, buyurtma berish/bekor qilish
│   └── admin.py             # Admin panel barcha funksiyalari
│
├── keyboards/
│   ├── common.py            # Umumiy klaviaturalar
│   ├── driver.py            # Haydovchi klaviaturalari
│   ├── passenger.py         # Yo'lovchi klaviaturalari
│   └── admin.py             # Admin klaviaturalari
│
└── states/
    ├── driver_states.py     # Haydovchi FSM holatlari
    ├── passenger_states.py  # Yo'lovchi FSM holatlari
    └── admin_states.py      # Admin FSM holatlari
```

---

## ⚙️ O'rnatish

### 1. `.env` faylini yarating

```bash
cp .env.example .env
```

`.env` faylini to'ldiring:

```env
BOT_TOKEN=7xxxxxxxxx:AAxxxxxxxx
DATABASE_URL=postgresql+asyncpg://user:password@host:5432/dbname
ADMIN_ID=123456789
DRIVERS_CHANNEL_ID=-1001234567890
ORDERS_CHANNEL_ID=-1009876543210
ADMIN_USERNAME=your_admin_username
```

### 2. Kutubxonalarni o'rnating

```bash
pip install -r requirements.txt
```

### 3. Botni ishga tushiring

```bash
python main.py
```

---

## 🚀 Railway.app ga deploy qilish

1. GitHub repoga push qiling
2. Railway.app da yangi project yarating → GitHub repo ni ulang
3. **Variables** bo'limida barcha `.env` o'zgaruvchilarini qo'shing
4. **PostgreSQL** plugin qo'shing — `DATABASE_URL` avtomatik beriladi
5. Deploy tugmasini bosing

---

## 🔐 Xavfsizlik arxitekturasi

### Race Condition himoyasi
`claim_order_atomic()` funksiyasi ichida:
```sql
SELECT * FROM orders WHERE id = ? FOR UPDATE
SELECT * FROM drivers WHERE user_id = ? FOR UPDATE
```
Ikkala qator ham bir vaqtda qulflanadi. Birinchi tranzaksiya tugaguncha boshqa haydovchi kutadi.

### ACID Atomarlik
Balans yechish + status o'zgartirish → bitta `BEGIN...COMMIT` ichida. Xato bo'lsa → avtomatik `ROLLBACK`.

### Buyurtma bekor qilish himoyasi
Status `CLAIMED` bo'lsa, yo'lovchi bekor qila olmaydi — xabar beriladi.

---

## 👤 Foydalanuvchi rollari

| Rol | Tavsif |
|-----|--------|
| Yo'lovchi | Buyurtma beradi |
| Haydovchi | Ro'yxatdan o'tadi, buyurtma oladi |
| Admin | Barcha boshqaruv funksiyalari |

---

## 📋 Admin buyruqlari

- `/admin` — Admin panelini ochish
- `➕ Balansni to'ldirish` — Haydovchi ID + summa
- `➖ Balansni ayirish` — Haydovchi ID + summa
- `💱 Komissiyani tahrirlash` — Yangi komissiya ($)
- `📊 Statistika` — Foydalanuvchilar, haydovchilar, zakazlar
- `📣 Reklama yuborish` — Matn/rasm/video/audio barcha userlarga
