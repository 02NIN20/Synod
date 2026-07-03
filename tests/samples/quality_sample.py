"""Intentionally low-quality sample: no security issues, only quality/architecture problems."""


class UserManager:
    def __init__(self):
        self.users = []
        self.logs = []
        self.cache = {}
        self.config = {}
        self.temp_data = []

    def add_user(self, name, email, age, address, phone, country, city, zip_code, status):
        user = {}
        user["name"] = name
        user["email"] = email
        user["age"] = age
        user["address"] = address
        user["phone"] = phone
        user["country"] = country
        user["city"] = city
        user["zip_code"] = zip_code
        user["status"] = status
        self.users.append(user)
        self.logs.append("added user")
        return user

    def process_user_data(self, data):
        if data:
            if data.get("type") == "premium":
                if data.get("status") == "active":
                    if data.get("age", 0) > 18:
                        if data.get("country") == "US":
                            if data.get("verified"):
                                return "process_premium_us_verified"
                            else:
                                return "process_premium_us_unverified"
                        else:
                            return "process_premium_international"
                    else:
                        return "process_premium_minor"
                else:
                    return "process_inactive"
            else:
                return "process_basic"
        return "no_data"


def calculate_stuff(a, b, c, d, e, f, g, h):
    x1 = a + b
    x2 = x1 * c
    x3 = x2 - d
    x4 = x3 / e if e != 0 else 0
    x5 = x4 + f
    x6 = x5 * g
    x7 = x6 - h
    return x7


def duplicate_logic_a(items):
    total = 0
    for item in items:
        if item > 0:
            total += item * 2
    return total


def duplicate_logic_b(values):
    total = 0
    for value in values:
        if value > 0:
            total += value * 2
    return total


class DataProcessor:
    def do_everything(self, raw_input):
        parsed = self._parse(raw_input)
        validated = self._validate(parsed)
        transformed = self._transform(validated)
        enriched = self._enrich(transformed)
        cached = self._cache(enriched)
        logged = self._log(cached)
        notified = self._notify(logged)
        persisted = self._persist(notified)
        return persisted

    def _parse(self, x): return x
    def _validate(self, x): return x
    def _transform(self, x): return x
    def _enrich(self, x): return x
    def _cache(self, x): return x
    def _log(self, x): return x
    def _notify(self, x): return x
    def _persist(self, x): return x


GLOBAL_STATE = {}


def update_global(key, value):
    GLOBAL_STATE[key] = value


def get_global(key):
    return GLOBAL_STATE.get(key)
