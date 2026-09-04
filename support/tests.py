from django.test import TestCase
from django.urls import reverse

from .models import SupportTicket


class SupportTests(TestCase):
    def test_pages_render(self):
        for name in ("support:faq", "support:contact", "support:shipping_returns", "support:privacy", "support:terms"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_contact_creates_ticket(self):
        r = self.client.post(
            reverse("support:contact"),
            {"name": "A", "email": "a@example.com", "order_number": "bnb-1001", "category": "sizing", "message": "Between S and M for the slip dress?"},
        )
        self.assertRedirects(r, reverse("support:contact"))
        t = SupportTicket.objects.get()
        self.assertEqual((t.order_number, t.category, t.status), ("BNB-1001", "sizing", "open"))

    def test_validation_and_honeypot(self):
        r = self.client.post(reverse("support:contact"), {"email": "a@example.com", "category": "other", "message": "hi"})
        self.assertContains(r, "little more detail")
        r = self.client.post(reverse("support:contact"), {"email": "a@example.com", "category": "other", "message": "spam spam spam spam", "website": "http://x"})
        self.assertEqual(SupportTicket.objects.count(), 0)
        self.assertEqual(r.status_code, 200)
