"""Questions people actually DM us. Rendered on /faq and on product pages."""

from django.utils.html import format_html

from catalog.placeholders import owner

FAQ = [
    {
        "group": "Ordering",
        "items": [
            ("Do I need an account?", "No. Bag, address, pay, done. Your order number and a link land on the confirmation page — screenshot it, and you can always look it up on the Track page with your email."),
            ("Is cash on delivery available?", "No. Everything is prepaid through Razorpay — UPI, cards, net banking, wallets. It keeps prices honest and lets us cut tiny batches without returns-to-origin eating us alive."),
            ("Why is a size missing?", "Small batch means small numbers. Each style is cut in 10–20 pieces total. When a size is gone it's usually gone for good, so if it's in stock and you're sure, don't sleep on it."),
            ("Can I change my order after paying?", "If we haven't packed it yet, yes — message us on the Contact page with your order number within a few hours and we'll swap the size or address."),
        ],
    },
    {
        "group": "Shipping",
        "items": [
            (
                "How long does delivery take?",
                format_html(
                    "We dispatch in {} from {}. Delivery takes {} after that. Free shipping across India on all prepaid orders.",
                    owner("dispatch window"), owner("dispatch city"), owner("delivery window"),
                ),
            ),
            ("Do you ship to hostels and PGs?", "Yes, and we know the gate situation. Put the gate timings or warden's name in the note at checkout and we pass it on to the courier."),
            ("Do you ship outside India?", "Not yet. If you're abroad and desperate, send us a note — we've been known to make a plan."),
            ("How do I track my parcel?", "Once it's shipped we add the courier and tracking number to your order. Use the Track page with your order number and email."),
        ],
    },
    {
        "group": "Fit & care",
        "items": [
            ("Which size am I?", "Check the size guide — it's body measurements, not garment measurements, and most of our styles are cut relaxed. Between sizes? Go down for dresses and co-ords, stay put for kaftans (they're one-size anyway)."),
            ("Are the fabrics see-through?", "Cover-ups are meant to be sheer. Kaftans and dresses are lined where it matters or cut in an opaque weight. Every product page says exactly what it's made of."),
            ("How do I wash them?", "Gentle machine wash cold, inside out, and line dry in the shade. Skip the dryer and the bleach."),
        ],
    },
    {
        "group": "Returns & defects",
        "items": [
            ("Can I return or exchange something?", "Returns are for defects only, reported within 3–5 days of delivery. There are no returns or exchanges for fit or change of mind, so check the size guide before you order."),
            ("What if something arrives damaged?", "Write to us from the Contact page with a photo within 3–5 days of delivery and we'll replace it or refund you, your call. We check every piece before it goes out, but couriers are couriers."),
            ("Do you do refunds?", "Only for defects, reported within 3–5 days of delivery. Small batches don't survive a return culture, and we'd rather keep prices where they are."),
        ],
    },
]


def flat():
    return [(q, a) for group in FAQ for (q, a) in group["items"]]
