from django import forms

from .models import SupportTicket


class ContactForm(forms.ModelForm):
    website = forms.CharField(required=False, widget=forms.HiddenInput)  # honeypot

    class Meta:
        model = SupportTicket
        fields = ["name", "email", "order_number", "category", "message"]
        labels = {"name": "Name", "email": "Email", "order_number": "Order number (if you have one)", "category": "What's this about?", "message": "Tell us"}
        widgets = {"message": forms.Textarea(attrs={"rows": 5})}

    def clean_message(self):
        msg = self.cleaned_data["message"].strip()
        if len(msg) < 10:
            raise forms.ValidationError("A little more detail helps us fix it faster.")
        return msg

    def clean_order_number(self):
        return self.cleaned_data["order_number"].strip().upper()

    def clean(self):
        data = super().clean()
        if data.get("website"):
            raise forms.ValidationError("Spam check failed.")
        return data
