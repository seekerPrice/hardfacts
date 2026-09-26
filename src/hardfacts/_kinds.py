"""The Kinds of Hard fact, with the words used for each when talking to a model or a person."""

KIND_NAMES = {
    "quantity": "number",
    "percent": "percentage",
    "money": "amount",
    "temperature": "temperature",
    "date": "date",
    "time": "time",
    "phone": "phone number",
    "email": "email address",
    "url": "link",
    "identifier": "ID or code",
}
KINDS = frozenset(KIND_NAMES)
