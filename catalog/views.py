from django.db.models import Prefetch
from django.http import Http404
from django.shortcuts import get_object_or_404, render

from .models import Category, Product, Variant
from .sizes import SIZE_CHART

SORTS = {
    "new": ("Newest", ["-sort_weight", "-created_at"]),
    "low": ("Price: low to high", ["price_inr", "name"]),
    "high": ("Price: high to low", ["-price_inr", "name"]),
}


def live_products():
    return Product.objects.live().prefetch_related("variants", "images")


def home(request):
    products = list(live_products())
    featured = [p for p in products if p.is_featured][:4]
    if len(featured) < 4:
        featured += [p for p in products if p not in featured][: 4 - len(featured)]
    kaftans = [p for p in products if p.category == "kaftans"][:3]
    new_in = [p for p in products if p not in featured and p not in kaftans][:4] or products[:4]
    return render(
        request,
        "catalog/home.html",
        {
            "featured": featured,
            "new_in": new_in,
            "kaftans": kaftans,
            "categories": Category.all(),
            "product_count": len(products),
        },
    )


def shop(request, category=None):
    cat = None
    if category:
        cat = Category.get(category)
        if cat is None:
            raise Http404
    sort = request.GET.get("sort", "new")
    if sort not in SORTS:
        sort = "new"
    qs = live_products().order_by(*SORTS[sort][1])
    if cat:
        qs = qs.filter(category=cat.slug)
    products = list(qs)
    if request.GET.get("size"):
        size = request.GET["size"]
        products = [p for p in products if any(v.size == size and v.stock > 0 for v in p.variants.all())]
    return render(
        request,
        "catalog/shop.html",
        {
            "category": cat,
            "categories": Category.all(),
            "products": products,
            "sort": sort,
            "sorts": [(k, v[0]) for k, v in SORTS.items()],
            "size_filter": request.GET.get("size", ""),
            "size_options": ["XS", "S", "M", "L", "XL", "FREE"],
        },
    )


def product_detail(request, slug):
    product = get_object_or_404(live_products(), slug=slug)
    related = list(live_products().filter(category=product.category).exclude(pk=product.pk)[:4])
    if len(related) < 4:
        related += list(live_products().exclude(pk=product.pk).exclude(pk__in=[p.pk for p in related])[: 4 - len(related)])
    variants = product.sized_variants()
    available = [v for v in variants if v.stock > 0]
    return render(
        request,
        "catalog/product.html",
        {
            "product": product,
            "variants": variants,
            "available": available,
            "images": product.ordered_images(),
            "related": related,
            "selected_size": request.GET.get("size", ""),
        },
    )


def about(request):
    return render(request, "catalog/about.html")


def size_guide(request):
    return render(request, "catalog/size_guide.html", {"chart": SIZE_CHART})


def not_found(request, exception=None):
    return render(request, "404.html", status=404)


def server_error(request):
    return render(request, "500.html", status=500)
