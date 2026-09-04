"""
Launch catalogue. Loaded by `manage.py seed_catalog`.
Image filenames follow tools/render_imagery.py: <slug>-1/2/3.svg.
"""

# The launch categories. The migration that introduced the Category model
# creates the same five; seed_catalog keeps their copy and images current.
CATEGORIES = [
    {"slug": "kaftans", "name": "Kaftans", "short": "Kaftan", "blurb": "One size, zero effort. Throw it on over anything, or nothing.", "image": "cat-kaftans.svg"},
    {"slug": "cover-ups", "name": "Cover-ups", "short": "Cover-up", "blurb": "Sheer, breezy, and doing the absolute minimum amount of covering.", "image": "cat-cover-ups.svg"},
    {"slug": "dresses", "name": "Resort dresses", "short": "Dress", "blurb": "From breakfast buffet to sunset bar without a costume change.", "image": "cat-dresses.svg"},
    {"slug": "co-ord-sets", "name": "Co-ord sets", "short": "Co-ord", "blurb": "Two pieces, one decision. Wear them together, or split them up.", "image": "cat-co-ord-sets.svg"},
    {"slug": "shorts-sets", "name": "Shorts sets", "short": "Shorts set", "blurb": "Shirt and shorts that look like you planned it. You didn't.", "image": "cat-shorts-sets.svg"},
]

FITTED = {"XS": 2, "S": 4, "M": 4, "L": 3, "XL": 2}
ONE_SIZE = {"FREE": 14}

CARE_DEFAULT = "Gentle machine wash cold, inside out. Line dry in the shade. Cool iron if you must."

PRODUCTS = [
    # ------------------------------------------------------------- kaftans
    {
        "slug": "sundowner-kaftan",
        "name": "Sundowner Kaftan",
        "category": "kaftans",
        "price_inr": 2499,
        "tagline": "The one you'll wear from the pool to the pizza place.",
        "print_name": "Tide Stripe",
        "colourway": "Bay blue on cream",
        "fabric": "100% cotton mulmul, 80 gsm. Light enough to pack in a tote, opaque enough to wear over a swimsuit or nothing.",
        "fit_note": "One size, cut wide and long with a deep V and tassel tie. Sits mid-calf on 5'4\".",
        "model_note": "Fits UK 6–16. Length 122 cm from shoulder.",
        "batch_size": 14,
        "stock": ONE_SIZE,
        "featured": True,
        "sort_weight": 50,
        "description": (
            "Hand-screened waves on soft mulmul that gets softer every wash. The Sundowner is the kaftan we started the label for: "
            "long enough to be a dress, light enough to forget you're wearing it, and cut wide so you can eat the whole thali.\n\n"
            "Deep V neck with a self-fabric tassel tie. Side slits to the knee. No lining, no fuss, no drama at the airport."
        ),
    },
    {
        "slug": "do-not-disturb-kaftan",
        "name": "Do Not Disturb Kaftan",
        "category": "kaftans",
        "price_inr": 2299,
        "tagline": "Room service, curtains drawn, phone on silent.",
        "print_name": "Sunspot",
        "colourway": "Cream on bay blue",
        "fabric": "Cotton-modal blend, 110 gsm. Drapes like a sheet you don't want to get out of.",
        "fit_note": "One size. Slightly shorter than the Sundowner, with a scooped back neck. Sits just below the knee.",
        "model_note": "Fits UK 6–16. Length 108 cm from shoulder.",
        "batch_size": 16,
        "stock": ONE_SIZE,
        "featured": True,
        "sort_weight": 48,
        "description": (
            "Polka dots the size of a two-rupee coin, printed cream on our signature blue. The Do Not Disturb has a scooped neck "
            "front and back so it slides on without wrecking your hair.\n\n"
            "Wear it as a nightie, a beach dress, or the thing you throw on to answer the door for the food delivery. We won't judge; we designed it for exactly that."
        ),
    },
    {
        "slug": "palm-reader-kaftan",
        "name": "Palm Reader Kaftan",
        "category": "kaftans",
        "price_inr": 2799,
        "tagline": "We see a long weekend in your future.",
        "print_name": "Fern Palm",
        "colourway": "Bay blue on cream",
        "fabric": "Cotton voile, 70 gsm, with a slight sheen. Semi-sheer at the sleeves, opaque through the body.",
        "fit_note": "One size. Wide batwing sleeves, tassel tie, deep side slits. Sits mid-calf.",
        "model_note": "Fits UK 6–16. Length 124 cm from shoulder.",
        "batch_size": 12,
        "stock": ONE_SIZE,
        "featured": False,
        "sort_weight": 44,
        "description": (
            "Big, loose fronds in blue on a cream voile that catches the light. This is the dressiest of the kaftans: the voile has a bit of a sheen, "
            "and the sleeves float rather than hang.\n\n"
            "Belt it for dinner, unbelt it for the boat. Our founder wore hers to a wedding in Alibaug and got asked where it was from nine times. Hence the batch of twelve."
        ),
    },
    {
        "slug": "late-checkout-kaftan",
        "name": "Late Checkout Kaftan",
        "category": "kaftans",
        "price_inr": 1999,
        "tagline": "Solid blue, zero decisions.",
        "print_name": "Solid",
        "colourway": "Bay blue with cream neck trim",
        "fabric": "Yarn-dyed cotton cambric, 95 gsm. Crisp on day one, lived-in by day three.",
        "fit_note": "One size. Cream contrast binding at the neck and a tassel tie. Sits mid-calf.",
        "model_note": "Fits UK 6–16. Length 120 cm from shoulder.",
        "batch_size": 20,
        "stock": ONE_SIZE,
        "featured": False,
        "sort_weight": 40,
        "description": (
            "Our blue, un-interrupted. Yarn-dyed so the colour goes all the way through the cloth instead of sitting on top, "
            "which is a long way of saying it won't fade to lavender.\n\n"
            "Cream binding at the V-neck and a tassel tie are the only details. Pairs with every other thing on this site, on purpose."
        ),
    },
    # ----------------------------------------------------------- cover-ups
    {
        "slug": "sheer-audacity-cover-up",
        "name": "Sheer Audacity Cover-up",
        "category": "cover-ups",
        "price_inr": 1699,
        "tagline": "Covering approximately nothing, beautifully.",
        "print_name": "Scallop Shell",
        "colourway": "Bay blue on cream",
        "fabric": "Cotton net with a scalloped print, 45 gsm. Sheer. That's the point.",
        "fit_note": "One size. Open front, wide sleeves, waist ties. Sits above the knee.",
        "model_note": "Fits UK 6–16. Length 96 cm from shoulder.",
        "batch_size": 18,
        "stock": ONE_SIZE,
        "featured": True,
        "sort_weight": 42,
        "description": (
            "A kimono-style cover-up in cotton net with tiny blue scallops running across it like a very organised tide. "
            "Open at the front with self-fabric ties at the waist so you can wear it loose over a swimsuit or knotted over a slip dress.\n\n"
            "Dries in about ten minutes on a balcony railing, which we've tested extensively."
        ),
    },
    {
        "slug": "beach-please-cover-up",
        "name": "Beach Please Cover-up",
        "category": "cover-ups",
        "price_inr": 1899,
        "tagline": "For the ones who arrive at the beach in an outfit.",
        "print_name": "Zig",
        "colourway": "Cream on bay blue",
        "fabric": "Cotton crepe, 65 gsm. Sheer in daylight, mostly not by sunset.",
        "fit_note": "One size. Open front with a longer, mid-calf line and side slits.",
        "model_note": "Fits UK 6–16. Length 118 cm from shoulder.",
        "batch_size": 14,
        "stock": ONE_SIZE,
        "featured": False,
        "sort_weight": 36,
        "description": (
            "Long, open, and covered in a cream zigzag on blue crepe. The Beach Please is the cover-up that reads as a coat, "
            "so you can wear it with jeans in the city when you get home and miss the sea.\n\n"
            "No ties, no closures. It stays put because the crepe has a bit of grip; trust it."
        ),
    },
    # ------------------------------------------------------------- dresses
    {
        "slug": "picnic-gone-wrong-slip-dress",
        "name": "Picnic Gone Wrong Slip Dress",
        "category": "dresses",
        "price_inr": 2999,
        "tagline": "Gingham, but make it a Tuesday night.",
        "print_name": "Gingham",
        "colourway": "Bay blue on cream",
        "fabric": "Yarn-dyed cotton gingham, 120 gsm, fully lined in cream cotton.",
        "fit_note": "Cut close through the bust with a bias-cut skirt that skims rather than clings. Adjustable straps. Sits mid-calf.",
        "model_note": "Model is 5'5\" and wears S.",
        "batch_size": 15,
        "stock": FITTED,
        "featured": True,
        "sort_weight": 46,
        "description": (
            "A bias-cut slip in a proper yarn-dyed gingham, the kind with the woven check, not a printed one. Sweetheart neckline, "
            "thin adjustable straps, and a skirt cut on the bias so it moves when you do.\n\n"
            "Fully lined, because we've all bought the one that wasn't. Wear it with sandals at brunch and with a cardigan and boots when the sea breeze turns."
        ),
    },
    {
        "slug": "sun-salutation-tiered-dress",
        "name": "Sun Salutation Tiered Dress",
        "category": "dresses",
        "price_inr": 3499,
        "tagline": "Three tiers. Twirl responsibly.",
        "print_name": "Little Sun",
        "colourway": "Bay blue on cream",
        "fabric": "Cotton cambric, 95 gsm. Opaque, lined at the bodice.",
        "fit_note": "Fitted bodice with cap sleeves and a blue grosgrain waistband, then three tiers to the ankle. Concealed side zip.",
        "model_note": "Model is 5'7\" and wears M.",
        "batch_size": 12,
        "stock": FITTED,
        "featured": False,
        "sort_weight": 45,
        "description": (
            "Tiny suns scattered over cream cambric, cut into a tiered maxi with a fitted bodice and cap sleeves. The waistband is a blue grosgrain "
            "ribbon stitched on, so it holds its shape after the fourth wash.\n\n"
            "This is the dress for the day you have plans and no idea what they are. Pockets in the first tier, obviously."
        ),
    },
    {
        "slug": "golden-hour-maxi-dress",
        "name": "Golden Hour Maxi Dress",
        "category": "dresses",
        "price_inr": 3999,
        "tagline": "Every photo you take in it will be a little too good.",
        "print_name": "Ditsy Bloom",
        "colourway": "Cream on bay blue",
        "fabric": "Cotton-viscose blend, 105 gsm. Drapey, opaque, fully lined at the bodice and first tier.",
        "fit_note": "Fitted bodice, cap sleeves, three soft tiers to the floor. Concealed side zip. Sits at the ankle on 5'5\".",
        "model_note": "Model is 5'5\" and wears S.",
        "batch_size": 10,
        "stock": {"XS": 1, "S": 3, "M": 3, "L": 2, "XL": 1},
        "featured": True,
        "sort_weight": 49,
        "description": (
            "Small cream flowers on blue, on a blend that falls like water. The Golden Hour is the one we cut the fewest of, because the fabric was "
            "a single bolt from a mill in Erode and we refused to substitute it.\n\n"
            "Fitted at the top, then it just goes. Wear it barefoot at a beach wedding or with white sneakers to a college fest. Both have happened."
        ),
    },
    {
        "slug": "room-service-slip-dress",
        "name": "Room Service Slip Dress",
        "category": "dresses",
        "price_inr": 2699,
        "tagline": "Solid, slinky, and ready in four seconds.",
        "print_name": "Solid",
        "colourway": "Bay blue",
        "fabric": "Cotton satin, 110 gsm. Matte on the inside, a whisper of sheen on the outside. Lined at the bodice.",
        "fit_note": "Bias-cut with a cowl-ish neckline and thin straps. Skims the body. Sits mid-calf.",
        "model_note": "Model is 5'6\" and wears M.",
        "batch_size": 16,
        "stock": FITTED,
        "featured": False,
        "sort_weight": 38,
        "description": (
            "A solid-blue slip in cotton satin: the fabric that looks like silk in a photo and behaves like cotton in a suitcase. "
            "Bias-cut so it drapes, thin straps, a soft cowl at the front.\n\n"
            "Layer the Sheer Audacity over it, or wear it alone and let it do the talking."
        ),
    },
    # --------------------------------------------------------- co-ord sets
    {
        "slug": "main-character-co-ord",
        "name": "Main Character Co-ord",
        "category": "co-ord-sets",
        "price_inr": 4499,
        "tagline": "Crop shirt and wide-leg pants. The rest of the trip is B-roll.",
        "print_name": "Diamond Ikat",
        "colourway": "Bay blue on cream",
        "fabric": "Cotton slub, 130 gsm. Structured enough to hold a shape, soft enough to nap in.",
        "fit_note": "Boxy cropped shirt with a notch neck and cuffed sleeves. Wide pants with an elasticated back waist and side pockets.",
        "model_note": "Model is 5'5\" and wears S in both.",
        "batch_size": 12,
        "stock": FITTED,
        "featured": True,
        "sort_weight": 47,
        "description": (
            "A diamond print that nods to ikat without pretending to be one, on a slubby cotton with visible texture. The shirt is cropped and boxy; "
            "the pants are wide, long, and have real pockets that fit a phone.\n\n"
            "Sold as a set, worn as whatever you like. The pants with a white vest. The shirt with denim. Together, when you need people to look."
        ),
    },
    {
        "slug": "stripe-tease-co-ord",
        "name": "Stripe Tease Co-ord",
        "category": "co-ord-sets",
        "price_inr": 4299,
        "tagline": "Bold stripe, boxy top, pants that mean business.",
        "print_name": "Deckchair Stripe",
        "colourway": "Bay blue on cream",
        "fabric": "Yarn-dyed cotton stripe, 125 gsm. Opaque, breathes, doesn't cling.",
        "fit_note": "Cropped shirt with a notch neck; wide pants with an elasticated back waist. Stripes matched at the side seams.",
        "model_note": "Model is 5'8\" and wears M in both.",
        "batch_size": 14,
        "stock": FITTED,
        "featured": False,
        "sort_weight": 41,
        "description": (
            "A fat horizontal stripe woven into the cloth, not printed on it. We match the stripes at every seam, which takes an unreasonable amount "
            "of extra fabric and is exactly why it looks the way it does.\n\n"
            "Cropped shirt, wide pants, pockets. Wear it to the airport and get upgraded. Results not guaranteed but reported."
        ),
    },
    {
        "slug": "out-of-office-co-ord",
        "name": "Out of Office Co-ord",
        "category": "co-ord-sets",
        "price_inr": 3999,
        "tagline": "Auto-reply on. Polka dots also on.",
        "print_name": "Sunspot",
        "colourway": "Bay blue on cream",
        "fabric": "Cotton poplin, 110 gsm. Crisp, opaque, cool.",
        "fit_note": "Cropped shirt with a notch neck and short sleeves; wide-leg pants with an elasticated back waist and pockets.",
        "model_note": "Model is 5'4\" and wears XS in both.",
        "batch_size": 16,
        "stock": FITTED,
        "featured": False,
        "sort_weight": 39,
        "description": (
            "Blue polka dots on cream poplin, cut into the same boxy shirt and wide pants as the rest of the co-ords. Poplin holds a crease, "
            "so this one looks intentional even after a six-hour bus.\n\n"
            "Set the auto-reply. Pack this. Go."
        ),
    },
    # -------------------------------------------------------- shorts sets
    {
        "slug": "boardwalk-shorts-set",
        "name": "Boardwalk Shorts Set",
        "category": "shorts-sets",
        "price_inr": 3299,
        "tagline": "Camp shirt and shorts, cut for chai on a pier.",
        "print_name": "Tide Stripe",
        "colourway": "Cream on bay blue",
        "fabric": "Cotton poplin, 110 gsm. Opaque, crisp, breathes.",
        "fit_note": "Relaxed camp-collar shirt with a chest pocket; mid-thigh shorts with an elasticated waist and pockets.",
        "model_note": "Model is 5'5\" and wears S in both.",
        "batch_size": 15,
        "stock": FITTED,
        "featured": True,
        "sort_weight": 43,
        "description": (
            "Cream waves on blue poplin. A relaxed camp-collar shirt with a real chest pocket and shorts that hit mid-thigh and have real pockets too. "
            "This is the set you buy for one trip and then wear every weekend for a year.\n\n"
            "Shirt and shorts are cut from the same bolt so the blues match, which sounds obvious and isn't."
        ),
    },
    {
        "slug": "lazy-sunday-shorts-set",
        "name": "Lazy Sunday Shorts Set",
        "category": "shorts-sets",
        "price_inr": 2999,
        "tagline": "Technically pyjamas. Legally an outfit.",
        "print_name": "Zig",
        "colourway": "Bay blue on cream",
        "fabric": "Cotton cambric, 95 gsm. Soft, opaque, gets better with washing.",
        "fit_note": "Relaxed camp-collar shirt and mid-thigh shorts with an elasticated waist.",
        "model_note": "Model is 5'6\" and wears M in both.",
        "batch_size": 18,
        "stock": FITTED,
        "featured": False,
        "sort_weight": 35,
        "description": (
            "Blue zigzags on cream cambric, in the shirt-and-shorts shape that works for sleeping, swimming-adjacent activities, and the 11am "
            "walk to the bakery. Coconut-shell buttons, because the plastic ones felt wrong.\n\n"
            "Wear the shirt open over a swimsuit, or buttoned up with the shorts and pretend you meant it."
        ),
    },
    {
        "slug": "sea-legs-shorts-set",
        "name": "Sea Legs Shorts Set",
        "category": "shorts-sets",
        "price_inr": 3499,
        "tagline": "Palms on blue. Sea legs optional.",
        "print_name": "Fern Palm",
        "colourway": "Cream on bay blue",
        "fabric": "Cotton-linen blend, 140 gsm. A little texture, a lot of breathing room.",
        "fit_note": "Relaxed camp-collar shirt with a chest pocket; shorts with an elasticated waist, side pockets and a slightly longer 6-inch inseam.",
        "model_note": "Model is 5'7\" and wears L in both.",
        "batch_size": 12,
        "stock": {"XS": 2, "S": 3, "M": 3, "L": 2, "XL": 2},
        "featured": False,
        "sort_weight": 37,
        "description": (
            "Cream palm fronds on blue, on a cotton-linen blend with a bit of crunch. The shorts run a touch longer than the others, for the ones "
            "who want to sit cross-legged on a ferry without thinking about it.\n\n"
            "Linen means it creases. We think that's the good part."
        ),
    },
]

IMAGE_ALTS = {
    1: "{name} in {print_name}, front view, flat on cream",
    2: "Close-up of the {print_name} print, {colourway}",
    3: "{name}, back view on bay blue",
}
