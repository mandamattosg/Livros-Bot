from decimal import Decimal
from app.database.session import SessionLocal
from app.models.product import Product
from app.models.price_history import PriceHistory
from app.services.price_drop_service import PriceDropService
from app.services.notification_service import NotificationService


db = SessionLocal()
product = db.query(Product)[2]
if not product:
    raise SystemExit('Nenhum produto encontrado no banco')

entry1 = PriceHistory(product_id=product.id, price=Decimal('100.00'))
entry2 = PriceHistory(product_id=product.id, price=Decimal('80.00'))
db.add(entry1)
db.add(entry2)
db.commit()
db.refresh(product)
product.price_history = db.query(PriceHistory).filter(PriceHistory.product_id == product.id).order_by(PriceHistory.checked_at.asc()).all()
drop = PriceDropService().detect_drop(product)
message = NotificationService(db)._build_message(product, drop)
print(drop)
print(message)

sent_count = NotificationService(db).send_drop_notification(drop, product)
print(f"Notificações enviadas: {sent_count}")
