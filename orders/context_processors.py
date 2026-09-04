from .cart import SESSION_KEY


def bag(request):
    data = request.session.get(SESSION_KEY, {}) if hasattr(request, "session") else {}
    return {"bag_count": sum(int(q) for q in data.values())}
