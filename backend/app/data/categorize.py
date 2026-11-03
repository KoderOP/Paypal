"""Rule-based categoriser used when an imported row has no category."""

RULES: list[tuple[str, tuple[str, ...]]] = [
    ("Income", ("salary", "payroll", "freelance", "upwork", "refund", "interest", "dividend", "payment received", "mass pay")),
    ("Rent", ("rent", "landlord")),
    ("Investments", ("sip", "mutual fund", "zerodha", "groww", "ppf", "fd ")),
    ("Subscriptions", ("netflix", "spotify", "prime", "youtube", "hotstar", "cult", "icloud", "google one")),
    ("Utilities", ("electricity", "bescom", "airtel", "jio", "broadband", "act fibernet", "water", "gas")),
    ("Groceries", ("bigbasket", "blinkit", "zepto", "dmart", "grocery", "instamart")),
    ("Food Delivery", ("swiggy", "zomato")),
    ("Dining Out", ("restaurant", "cafe", "dining")),
    ("Transport", ("uber", "ola", "rapido", "metro", "fuel", "petrol", "irctc")),
    ("Shopping", ("amazon", "flipkart", "myntra", "ajio", "croma")),
    ("Health", ("pharmacy", "apollo", "1mg", "hospital", "clinic", "dental")),
    ("Personal Care", ("urban company", "salon", "grooming")),
    ("Entertainment", ("bookmyshow", "pvr", "inox")),
    ("Travel", ("indigo", "makemytrip", "air india", "hotel", "flight")),
]

ESSENTIAL_CATEGORIES = {"Rent", "Utilities", "Groceries", "Transport", "Health"}
SAVINGS_CATEGORIES = {"Investments"}


def categorize(description: str, amount_is_credit: bool) -> str:
    text = description.lower()
    for category, keywords in RULES:
        if any(k in text for k in keywords):
            return category
    return "Other Income" if amount_is_credit else "Other"
