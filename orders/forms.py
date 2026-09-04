import re

from django import forms

from .models import STATE_CHOICES

PHONE_RE = re.compile(r"^[6-9]\d{9}$")
PIN_RE = re.compile(r"^[1-9]\d{5}$")


class CheckoutForm(forms.Form):
    customer_name = forms.CharField(label="Full name", max_length=120)
    email = forms.EmailField(label="Email", help_text="Your order confirmation lives here.")
    phone = forms.CharField(label="Mobile number", max_length=15, help_text="10 digits, for the courier.")
    address1 = forms.CharField(label="Flat, house, street", max_length=200)
    address2 = forms.CharField(label="Landmark, area", max_length=200, required=False)
    city = forms.CharField(label="City", max_length=80)
    state = forms.ChoiceField(label="State", choices=[("", "Pick a state")] + STATE_CHOICES)
    pincode = forms.CharField(label="PIN code", max_length=6)
    note = forms.CharField(
        label="Note for us", max_length=200, required=False, help_text="Gift? Hostel gate timings? Tell us."
    )

    def clean_phone(self):
        digits = re.sub(r"\D", "", self.cleaned_data["phone"])
        if digits.startswith("91") and len(digits) == 12:
            digits = digits[2:]
        if not PHONE_RE.match(digits):
            raise forms.ValidationError("Enter a 10-digit Indian mobile number.")
        return digits

    def clean_pincode(self):
        pin = self.cleaned_data["pincode"].strip()
        if not PIN_RE.match(pin):
            raise forms.ValidationError("That doesn't look like a 6-digit PIN code.")
        return pin

    def clean_customer_name(self):
        name = " ".join(self.cleaned_data["customer_name"].split())
        if len(name) < 2:
            raise forms.ValidationError("We need a name for the parcel.")
        return name


class TrackForm(forms.Form):
    order_number = forms.CharField(label="Order number", max_length=16, help_text="Looks like BNB-1042.")
    contact = forms.CharField(label="Email or mobile number", max_length=120)

    def clean_order_number(self):
        return self.cleaned_data["order_number"].strip().upper()
