"""
Money formatting for templates.

Prices are integer rupees everywhere in Python and the database. This filter
is the single place that turns one into the string a customer reads, with
Indian digit grouping: the last three digits, then pairs.

    999    -> "₹ 999"
    1000   -> "₹ 1,000"
    12500  -> "₹ 12,500"
    125000 -> "₹ 1,25,000"

The admin deliberately does not use it: the owner edits the same integer the
database stores.
"""
from django import template

register = template.Library()

RUPEE = "₹"


def group_indian(digits):
    """Group a run of digits the Indian way: three at the end, then twos."""
    if len(digits) <= 3:
        return digits
    head, tail = digits[:-3], digits[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    parts.append(tail)
    return ",".join(parts)


@register.filter
def rupees(value):
    """
    Format whole rupees as ``₹ 1,25,000``. Anything that is not a whole number
    is handed back untouched, so a template bug shows up as a visible oddity
    rather than a wrong price.
    """
    try:
        amount = int(value)
    except (TypeError, ValueError):
        return value
    sign = "-" if amount < 0 else ""
    return f"{sign}{RUPEE} {group_indian(str(abs(amount)))}"
