from django.contrib import messages
from django.shortcuts import redirect, render

from .faq import FAQ
from .forms import ContactForm


def faq(request):
    return render(request, "support/faq.html", {"faq": FAQ})


def contact(request):
    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Got it. A real human replies within a working day.")
            return redirect("support:contact")
    else:
        form = ContactForm(initial={"order_number": request.GET.get("order", "")})
    return render(request, "support/contact.html", {"form": form})


def shipping_returns(request):
    return render(request, "support/shipping_returns.html")


def privacy(request):
    return render(request, "support/privacy.html")


def terms(request):
    return render(request, "support/terms.html")
