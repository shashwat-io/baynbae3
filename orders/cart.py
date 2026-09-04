"""
Session bag. Stored as {variant_id: quantity} under session["bag"].
Nothing here is trusted for money — prices are re-read from the DB every time.
"""
from dataclasses import dataclass

from catalog.models import Variant

from .pricing import shipping_for

SESSION_KEY = "bag"
MAX_PER_LINE = 5


@dataclass
class Line:
    variant: Variant
    quantity: int

    @property
    def product(self):
        return self.variant.product

    @property
    def unit_price_inr(self):
        return self.product.price_inr

    @property
    def line_total_inr(self):
        return self.unit_price_inr * self.quantity

    @property
    def at_max(self):
        return self.quantity >= min(self.variant.stock, MAX_PER_LINE)


class Bag:
    def __init__(self, session):
        self.session = session
        self.data = dict(session.get(SESSION_KEY, {}))
        self.notices = []
        self._lines = None

    # -- persistence -----------------------------------------------------
    def save(self):
        self.session[SESSION_KEY] = self.data
        self.session.modified = True
        self._lines = None

    def clear(self):
        self.data = {}
        self.save()

    # -- mutation --------------------------------------------------------
    def add(self, variant, quantity=1):
        """Add up to `quantity`; clamps to stock and the per-line cap. Returns qty actually added."""
        if not variant.product.is_live or variant.stock <= 0:
            self.notices.append(f"{variant.product.name} in {variant.size_label} just sold out.")
            return 0
        key = str(variant.pk)
        current = self.data.get(key, 0)
        cap = min(variant.stock, MAX_PER_LINE)
        new = min(current + max(1, quantity), cap)
        added = new - current
        if added == 0:
            if current >= variant.stock:
                self.notices.append(f"That's every {variant.size_label} we have of the {variant.product.name}.")
            else:
                self.notices.append(f"Max {MAX_PER_LINE} of one size per order — small batch, share the love.")
        self.data[key] = new
        self.save()
        return added

    def set_quantity(self, variant, quantity):
        key = str(variant.pk)
        if quantity <= 0:
            self.data.pop(key, None)
        else:
            self.data[key] = min(quantity, variant.stock, MAX_PER_LINE)
        self.save()

    def remove(self, variant_id):
        self.data.pop(str(variant_id), None)
        self.save()

    # -- reading ---------------------------------------------------------
    def lines(self):
        """Live lines, syncing the session against current stock and live status."""
        if self._lines is not None:
            return self._lines
        ids = [int(k) for k in self.data.keys()]
        variants = {
            v.pk: v
            for v in Variant.objects.filter(pk__in=ids).select_related("product").prefetch_related("product__images")
        }
        lines, changed = [], False
        for key, qty in list(self.data.items()):
            v = variants.get(int(key))
            if v is None or not v.product.is_live or v.stock <= 0:
                name = v.product.name if v else "An item"
                self.notices.append(f"{name} sold out while it was in your bag. We've taken it out.")
                self.data.pop(key)
                changed = True
                continue
            if qty > v.stock:
                self.notices.append(f"Only {v.stock} left of {v.product.name} in {v.size_label} — bag updated.")
                qty = v.stock
                self.data[key] = qty
                changed = True
            lines.append(Line(v, qty))
        if changed:
            self.save()
        self._lines = lines
        return lines

    @property
    def count(self):
        return sum(int(q) for q in self.data.values())

    @property
    def is_empty(self):
        return not self.data

    @property
    def subtotal_inr(self):
        return sum(line.line_total_inr for line in self.lines())

    @property
    def shipping_inr(self):
        return shipping_for(self.subtotal_inr)

    @property
    def total_inr(self):
        return self.subtotal_inr + self.shipping_inr
