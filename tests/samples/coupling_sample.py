"""Quality-only sample: tight coupling, no security issues."""


class OrderProcessor:
    def process(self, order):
        # directly reaches into other modules' internals
        db = Database()
        db.connection.cursor().execute("UPDATE orders SET status='processing'")

        mailer = EmailService()
        mailer.smtp_client.connect()
        mailer.smtp_client.send(order.customer.email, "Order received")

        inventory = InventorySystem()
        inventory.warehouse.stock[order.item_id] -= order.quantity

        return order


class Database:
    def __init__(self):
        self.connection = FakeConnection()


class FakeConnection:
    def cursor(self):
        return self


class EmailService:
    def __init__(self):
        self.smtp_client = SmtpClient()


class SmtpClient:
    def connect(self): pass
    def send(self, to, msg): pass


class InventorySystem:
    def __init__(self):
        self.warehouse = Warehouse()


class Warehouse:
    def __init__(self):
        self.stock = {}


def handle_request(req, res, next_middleware, db, cache, logger, config, session):
    if req.method == "POST":
        if req.path == "/order":
            if req.body:
                if "item_id" in req.body:
                    if db.is_connected():
                        if cache.has(req.body["item_id"]):
                            logger.log("cache hit")
                        else:
                            logger.log("cache miss")
