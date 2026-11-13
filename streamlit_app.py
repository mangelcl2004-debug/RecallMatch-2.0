import json
import re
import urllib.error
import urllib.request
from urllib.parse import quote

import streamlit as st

st.set_page_config(
    page_title="RecallMatch | Food Intelligence",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700;800&display=swap');
html, body, [data-testid="stApp"] {font-family:'DM Sans',sans-serif;}
[data-testid="stApp"] {background:#080d0c;color:#f5f8f6;}
[data-testid="stSidebar"] {background:#101816;border-right:1px solid #26362f;}
.block-container {max-width:1250px;padding-top:2rem;padding-bottom:4rem;}
h1,h2,h3 {color:#f5f8f6!important;}
.rm-brand {font-size:25px;font-weight:800;color:#fff;}
.rm-subtitle {color:#43d9a0;font-size:11px;letter-spacing:3px;font-weight:700;}
.hero {background:linear-gradient(120deg,#123b2d,#10201b);border:1px solid #28664e;border-radius:22px;padding:32px;margin-bottom:25px;}
.hero h1 {font-size:36px;margin-bottom:8px;}
.hero p {color:#c3ded1;font-size:16px;}
.metric-card,.feature-card {background:#121b18;border:1px solid #2b3d34;border-radius:17px;padding:20px;}
.metric-card {min-height:125px;}
.metric-label {color:#a9c0b4;font-size:13px;}
.metric-value {font-size:27px;font-weight:800;color:#48dda2;}
.feature-card {min-height:145px;margin-bottom:10px;}
.feature-card h3 {font-size:18px;}
.feature-card p {color:#a9bcb1;font-size:13px;}
.stButton button {background:#087b57;color:white;border:1px solid #24b982;border-radius:10px;font-weight:700;}
.stButton button:hover {background:#11986c;color:white;}
@media(max-width:700px) {.hero{padding:22px}.hero h1{font-size:27px}.block-container{padding:1rem}}
</style>
""", unsafe_allow_html=True)


def lookup_open_food_facts(barcode: str):
    """Look up a barcode in the public Open Food Facts product database."""
    fields = (
        "product_name,product_name_en,brands,image_url,ingredients_text,"
        "allergens,allergens_tags,nutriscore_grade,nutriments,quantity,categories"
    )
    url = (
        f"https://world.openfoodfacts.org/api/v2/product/{barcode}.json"
        f"?fields={fields}"
    )
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "RecallMatch/2.0 (food product lookup)"}
    )
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Product database returned HTTP {exc.code}.") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError("Could not reach the product database. Check the internet connection and try again.") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("The product database returned an unreadable response.") from exc

    if data.get("status") != 1 or not data.get("product"):
        return None
    return data["product"]


def search_open_food_facts(search_term: str, page_size: int = 8):
    """Search Open Food Facts by product name or brand."""
    term = search_term.strip()
    if not term:
        raise ValueError("Enter a product name or brand.")

    fields = (
        "code,product_name,product_name_en,brands,quantity,image_url,"
        "nutriscore_grade,nutriments"
    )
    params = (
        f"search_terms={quote(term)}&search_simple=1&action=process&json=1"
        f"&page_size={int(page_size)}&fields={quote(fields)}"
    )
    url = f"https://world.openfoodfacts.org/cgi/search.pl?{params}"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "RecallMatch/2.0 (food comparison)"}
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Open Food Facts returned HTTP {exc.code} while searching.") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError("Could not reach Open Food Facts. Check the internet connection and try again.") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("Open Food Facts returned an unreadable search response.") from exc

    products = data.get("products") or []
    # Prefer a result whose name or brand contains the requested search words.
    terms = [word.lower() for word in re.findall(r"[a-zA-Z0-9]+", term) if len(word) > 1]
    def relevance(product):
        name = (product.get("product_name") or product.get("product_name_en") or "").lower()
        brand = (product.get("brands") or "").lower()
        text = f"{name} {brand}"
        return sum(3 if word in name else 1 if word in brand else 0 for word in terms)
    products = [p for p in products if p.get("product_name") or p.get("product_name_en")]
    products.sort(key=relevance, reverse=True)
    if not products or relevance(products[0]) == 0:
        return None
    return products[0]


def show_comparison_product(product, label: str):
    """Display a concise product summary and nutrition values per 100 g."""
    name = product.get("product_name") or product.get("product_name_en") or "Name not available"
    brand = product.get("brands") or "Brand not listed"
    nutriments = product.get("nutriments") or {}
    st.subheader(name)
    st.caption(f"{label} · {brand}")
    if product.get("image_url"):
        try:
            st.image(product["image_url"], use_container_width=True)
        except Exception:
            st.caption("Product image could not be loaded.")
    if product.get("quantity"):
        st.caption(f"Package: {product['quantity']}")
    if product.get("nutriscore_grade"):
        st.caption(f"Nutri-Score: {str(product['nutriscore_grade']).upper()}")
    values = [
        ("Calories", "energy-kcal_100g", "kcal"),
        ("Fat", "fat_100g", "g"),
        ("Saturated fat", "saturated-fat_100g", "g"),
        ("Carbohydrates", "carbohydrates_100g", "g"),
        ("Sugars", "sugars_100g", "g"),
        ("Fiber", "fiber_100g", "g"),
        ("Protein", "proteins_100g", "g"),
        ("Salt", "salt_100g", "g"),
    ]
    for title, key, unit in values:
        value = nutriments.get(key)
        if value is None:
            st.write(f"**{title}:** Not provided")
        else:
            try:
                st.write(f"**{title}:** {float(value):g} {unit} / 100 g")
            except (TypeError, ValueError):
                st.write(f"**{title}:** {value} {unit} / 100 g")
    return nutriments


def lookup_fda_food_recalls(search_term: str, limit: int = 10):
    """Search FDA's public openFDA food enforcement recall database."""
    term = search_term.strip()
    if not term:
        raise ValueError("Enter a product name, brand, or company to search.")
    safe_term = term.replace("\\", " ").replace('"', " ").strip()
    query = f'products.description:"{safe_term}" OR recalling_firm:"{safe_term}"'
    url = (
        "https://api.fda.gov/food/enforcement.json?"
        f"search={quote(query, safe='')}&limit={int(limit)}&sort=report_date:desc"
    )
    request = urllib.request.Request(
        url, headers={"User-Agent": "RecallMatch/2.0 (FDA food recall lookup)"}
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return []
        raise RuntimeError(f"FDA recall database returned HTTP {exc.code}.") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError("Could not reach the FDA recall database. Check the internet connection and try again.") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("The FDA recall database returned an unreadable response.") from exc
    return data.get("results", [])


ALLERGEN_TERMS = {
    "Milk": ["milk", "whey", "casein", "caseinate", "butter", "cream", "lactose"],
    "Egg": ["egg", "eggs", "albumin", "mayonnaise"],
    "Peanuts": ["peanut", "peanuts", "groundnut"],
    # Generic "nuts" is handled as an unspecified tree-nut declaration below;
    # it is deliberately NOT treated as peanuts.
    "Tree nuts": ["almond", "hazelnut", "walnut", "cashew", "pecan", "pistachio", "macadamia", "brazil nut", "nuts"],
    "Wheat": ["wheat", "wheat flour", "semolina", "spelt", "durum"],
    "Soy": ["soy", "soya", "soybean", "soybeans", "soya bean", "soya beans", "soy bean", "soy beans", "soy lecithin", "edamame"],
    "Fish": ["fish", "anchovy", "cod", "salmon", "tuna"],
    "Crustacean shellfish": ["crustacean", "shrimp", "prawn", "crab", "lobster", "crayfish"],
    "Sesame": ["sesame", "tahini"],
}


def find_allergen_matches(product, selected_allergens):
    """Match selected allergens against ingredient text and OFF allergen declarations.

    Open Food Facts may return declarations such as "en:soybeans" or the
    generic "en:nuts" tag. Normalize language prefixes and punctuation before
    matching. Generic nuts are associated with Tree nuts, never Peanuts.
    """
    ingredients = product.get("ingredients_text") or ""
    declared = product.get("allergens") or ""
    tags = product.get("allergens_tags") or []

    # Keep original text for evidence labels, but normalize OFF tags such as
    # "en:soybeans" into ordinary words for matching.
    raw_sources = [ingredients, declared, " ".join(str(tag) for tag in tags)]
    searchable = " ".join(raw_sources).lower()
    searchable = re.sub(r"\b[a-z]{2,3}:", " ", searchable)
    searchable = re.sub(r"[^a-z0-9]+", " ", searchable)

    matches = []
    for allergen in selected_allergens:
        terms = ALLERGEN_TERMS.get(allergen, [allergen.lower()])
        found_terms = []
        for term in terms:
            normalized_term = re.sub(r"[^a-z0-9]+", " ", term.lower()).strip()
            if not normalized_term:
                continue
            # Exact token/phrase boundaries avoid matching "soy" inside
            # unrelated words while allowing explicit plural variants above.
            pattern = r"(?<![a-z0-9])" + re.escape(normalized_term) + r"(?![a-z0-9])"
            if re.search(pattern, searchable):
                found_terms.append(term)
        if found_terms:
            matches.append((allergen, sorted(set(found_terms))))
    return matches, bool(ingredients or declared or tags)


def show_product(product, barcode, selected_allergens):
    name = product.get("product_name") or product.get("product_name_en") or "Name not available"
    brand = product.get("brands") or "Brand not available"
    image_url = product.get("image_url")
    nutriments = product.get("nutriments") or {}

    st.success("Product found in Open Food Facts.")
    left, right = st.columns([1, 2])
    with left:
        if image_url:
            try:
                st.image(image_url, use_container_width=True)
            except Exception:
                st.info("Product image could not be loaded.")
        else:
            st.info("No product image is available in the database.")
    with right:
        st.subheader(name)
        st.write(f"**Brand:** {brand}")
        st.write(f"**Barcode:** {barcode}")
        if product.get("quantity"):
            st.write(f"**Package size:** {product['quantity']}")
        if product.get("nutriscore_grade"):
            st.write(f"**Nutri-Score:** {str(product['nutriscore_grade']).upper()}")

    st.markdown("#### Nutrition information")
    nutrition_items = [
        ("Energy", "energy-kcal_100g", "kcal / 100 g"),
        ("Fat", "fat_100g", "g / 100 g"),
        ("Saturated fat", "saturated-fat_100g", "g / 100 g"),
        ("Carbohydrates", "carbohydrates_100g", "g / 100 g"),
        ("Sugars", "sugars_100g", "g / 100 g"),
        ("Fiber", "fiber_100g", "g / 100 g"),
        ("Protein", "proteins_100g", "g / 100 g"),
        ("Salt", "salt_100g", "g / 100 g"),
    ]
    cols = st.columns(4)
    for index, (label, key, unit) in enumerate(nutrition_items):
        value = nutriments.get(key)
        with cols[index % 4]:
            if value is not None:
                st.metric(label, f"{value} {unit}")
            else:
                st.caption(f"{label}: Not provided")

    st.markdown("#### Ingredients")
    ingredients = product.get("ingredients_text")
    st.write(ingredients if ingredients else "Ingredients are not listed in this database record.")

    st.markdown("#### Allergen safety check")
    declared = product.get("allergens") or ""
    st.write(f"**Allergens declared in the database:** {declared if declared else 'No allergen information listed.'}")

    if not selected_allergens:
        st.info("Choose your allergens above to run a personalized ingredient check.")
    else:
        matches, has_source_data = find_allergen_matches(product, selected_allergens)
        if matches:
            st.error("Potential allergen match found. Do not consume until you verify the complete package label and manufacturer information.")
            for allergen, terms in matches:
                st.write(f"- **{allergen}:** matching text — {', '.join(terms)}")
        elif has_source_data:
            st.success("No selected allergen terms were found in the available database text.")
            st.caption("This is not proof that the product is safe for you. Cross-contact and incomplete or outdated records may not be detected.")
        else:
            st.warning("The database does not contain enough ingredient/allergen information to check your selected allergens.")

    st.caption(
        "Source: Open Food Facts. Product records are community-contributed and may be incomplete or outdated. "
        "This screening is informational only, is not medical advice, and cannot guarantee allergen safety. "
        "Always read the package label and contact the manufacturer when needed."
    )


PAGES = ["Home", "Food Scanner", "Food Health Score", "FDA Recalls", "Compare Foods",
         "Food Diary", "Nutrition Calendar", "Recent Scans",
         "AI Nutrition Assistant", "My Account"]

if "page" not in st.session_state:
    st.session_state.page = "Home"
if "diary" not in st.session_state:
    st.session_state.diary = []
if "last_product" not in st.session_state:
    st.session_state.last_product = None

with st.sidebar:
    st.markdown('<div class="rm-brand">✦ RecallMatch</div>', unsafe_allow_html=True)
    st.markdown('<div class="rm-subtitle">FOOD INTELLIGENCE</div>', unsafe_allow_html=True)
    st.divider()
    st.markdown("### Navigation")
    st.session_state.page = st.radio(
        "Select a section", PAGES,
        index=PAGES.index(st.session_state.page),
        label_visibility="collapsed"
    )
    st.divider()
    st.caption("RecallMatch 2.0")
    st.caption("Your food intelligence companion.")

if st.session_state.page == "Home":
    st.markdown("""
    <div class="hero">
      <div style="color:#55e6ac;font-weight:800;letter-spacing:2px">FOOD INTELLIGENCE PLATFORM</div>
      <h1>Know Your Food.<br>Protect Your Health.</h1>
      <p>Scan food products, explore recalls, compare nutrition and make more informed food decisions.</p>
    </div>""", unsafe_allow_html=True)
    st.markdown("### Your Dashboard")
    c1,c2,c3 = st.columns(3)
    with c1:
        st.markdown('<div class="metric-card"><div class="metric-label">Food Scans</div><div class="metric-value">0</div><p>Your scanning activity</p></div>', unsafe_allow_html=True)
    with c2:
        st.markdown('<div class="metric-card"><div class="metric-label">Saved Foods</div><div class="metric-value">0</div><p>Your food collection</p></div>', unsafe_allow_html=True)
    with c3:
        st.markdown(f'<div class="metric-card"><div class="metric-label">Diary Entries</div><div class="metric-value">{len(st.session_state.diary)}</div><p>Your food diary</p></div>', unsafe_allow_html=True)
    st.markdown("### Explore RecallMatch")
    features = [
        ("📷","Food Scanner","Look up products by barcode."),
        ("🛡️","FDA Recalls","Check official food recall information."),
        ("⚖️","Compare Foods","Compare nutritional information between products."),
        ("📔","Food Diary","Record and organize your meals."),
        ("📅","Nutrition Calendar","Explore your nutrition activity."),
        ("🤖","AI Assistant","Get help understanding food and nutrition.")
    ]
    cols = st.columns(3)
    for i,(icon,title,description) in enumerate(features):
        with cols[i % 3]:
            st.markdown(f'<div class="feature-card"><div style="font-size:28px">{icon}</div><h3>{title}</h3><p>{description}</p></div>', unsafe_allow_html=True)
            if st.button("Open " + title, key=f"feature_{i}", use_container_width=True):
                st.session_state.page = title
                st.rerun()

elif st.session_state.page == "Food Scanner":
    st.title("📷 Food Scanner")
    st.write("Look up a packaged food product using its barcode.")
    barcode = st.text_input("Enter a product barcode", placeholder="Example: 049000028911")
    st.caption("You can type the digits below the barcode on the package.")
    st.markdown("#### Your allergen profile")
    st.write("Select the allergens you want RecallMatch to look for in product records.")
    selected_allergens = st.multiselect(
        "Allergens to check",
        options=list(ALLERGEN_TERMS.keys()),
        key="allergen_profile",
        help="This checks listed ingredient and allergen text only. It cannot detect cross-contact or guarantee safety."
    )
    photo = st.camera_input("Or take a product photo")
    if st.button("Search Product"):
        cleaned_barcode = "".join(ch for ch in barcode if ch.isdigit())
        if cleaned_barcode:
            with st.spinner("Searching Open Food Facts..."):
                try:
                    product = lookup_open_food_facts(cleaned_barcode)
                    if product:
                        st.session_state.last_product = (product, cleaned_barcode)
                        if "scan_history" not in st.session_state:
                            st.session_state.scan_history = []
                            
                        st.session_state.scan_history.append({
                            "name": product.get("product_name", "Unknown product"),
                            "barcode": cleaned_barcode
                        })
                    else:
                        st.session_state.last_product = None
                        st.warning("No matching product was found. Check the barcode and try again.")
                except RuntimeError as error:
                    st.error(str(error))
        elif photo:
            st.info("Photo recognition is not connected yet. Please enter the barcode digits for now.")
        else:
            st.warning("Enter a barcode first. Photo-based product recognition is not available yet.")

    if st.session_state.last_product:
        show_product(st.session_state.last_product[0], st.session_state.last_product[1], selected_allergens)

elif st.session_state.page == "Food Health Score":
    st.title("🥗 Food Health Score")
    st.write("Evaluate the nutritional quality of your scanned food product.")
    if st.session_state.last_product:
        product = st.session_state.last_product[0]
        nutriments = product.get("nutriments") or {}
        sugar = nutriments.get("sugars_100g")
        saturated_fat = nutriments.get("saturated-fat_100g")
        salt = nutriments.get("salt_100g")
        fiber = nutriments.get("fiber_100g")
        st.subheader(
            product.get("product_name")
            or product.get("product_name_en")
            or "Scanned Product"
        )
        values = {
            "Sugar": sugar,
            "Saturated Fat": saturated_fat,
            "Salt": salt,
            "Fiber": fiber
        }
        for name, value in values.items():
            if value is not None:
                st.write(f"**{name}:** {value} g / 100 g")
            else:
                st.warning(f"{name}: Data not available")
        if all(v is not None for v in values.values()):
            sugar_penalty = (
                30 if sugar > 30 else
                20 if sugar > 20 else
                10 if sugar > 10 else
                5 if sugar > 5 else 0
            )
            fat_penalty = (
                20 if saturated_fat > 5 else
                10 if saturated_fat > 3 else
                5 if saturated_fat > 1 else 0
            )
            salt_penalty = (
                20 if salt > 3 else
                10 if salt > 1.5 else
                5 if salt > 0.3 else 0
            )
            fiber_bonus = (
                10 if fiber >= 6 else
                5 if fiber >= 3 else 0
            )
            score = max(
                0,
                min(100, 100 - sugar_penalty
                    - fat_penalty - salt_penalty + fiber_bonus)
            )
            st.divider()
            st.metric("Food Health Score", f"{score}/100")
            if score >= 80:
                st.success("Good nutritional profile!")
            elif score >= 60:
                st.info("Moderate nutritional profile.")
            else:
                st.warning("This product has several nutritional factors to consider.")
        else:
            st.warning(
                "A complete score cannot be calculated because "
                "some nutritional information is missing."
            )
    else:
        st.info("Please scan a food product first using Food Scanner.")
    st.caption(
        "Experimental educational score based on sugar, saturated fat, "
        "salt and fiber. This is not an official Nutri-Score or medical advice."
    )
    
elif st.session_state.page == "FDA Recalls":
    st.title("🛡️ FDA Food Recalls")
    st.write("Search FDA food enforcement reports for recalled products, brands, or companies.")
    st.warning("A search with no results does not prove a product is safe. FDA records may be incomplete or delayed; always verify current notices and the package details.")
    recall_term = st.text_input("Search product, brand, or recalling company", placeholder="Example: peanut butter, spinach, or company name")
    if st.button("Search FDA Recalls", type="primary"):
        if not recall_term.strip():
            st.warning("Enter a product, brand, or company name first.")
        else:
            with st.spinner("Searching the FDA food enforcement database..."):
                try:
                    recall_results = lookup_fda_food_recalls(recall_term, limit=10)
                    if not recall_results:
                        st.info("No matching FDA food enforcement reports were returned for that search. Try a shorter product or brand name.")
                    else:
                        st.success(f"Found {len(recall_results)} matching FDA enforcement report(s).")
                        for item in recall_results:
                            products = item.get("products") or []
                            descriptions = [p.get("description", "") for p in products if p.get("description")]
                            with st.expander(f"{item.get('recalling_firm', 'Company not listed')} — {descriptions[0] if descriptions else 'Product description not listed'}"):
                                st.write(f"**Recall reason:** {item.get('reason_for_recall', 'Not listed')}")
                                st.write(f"**Status:** {item.get('status', 'Not listed')}")
                                st.write(f"**Classification:** {item.get('classification', 'Not listed')}")
                                st.write(f"**Recall initiation date:** {item.get('recall_initiation_date', 'Not listed')}")
                                st.write(f"**Report date:** {item.get('report_date', 'Not listed')}")
                                st.write(f"**Distribution:** {item.get('distribution_pattern', 'Not listed')}")
                                if descriptions:
                                    st.write("**Products:** " + "; ".join(descriptions))
                                if item.get("recall_number"):
                                    st.caption(f"FDA recall number: {item['recall_number']}")
                except (RuntimeError, ValueError) as exc:
                    st.error(str(exc))
    st.caption("Data source: FDA openFDA Food Enforcement API. This search covers FDA food enforcement records, not every food-safety alert or USDA-regulated meat and poultry recall. Verify details with the official FDA notices.")
    st.markdown("[Open FDA Recalls, Market Withdrawals, and Safety Alerts](https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts)")

elif st.session_state.page == "Compare Foods":
    st.title("⚖️ Compare Foods")
    st.write("Search two packaged foods in Open Food Facts and compare their nutrition per 100 g.")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Product 1")
        food1 = st.text_input("First food product", placeholder="Example: Nutella", key="compare_food_1")
    with col2:
        st.subheader("Product 2")
        food2 = st.text_input("Second food product", placeholder="Example: Peanut Butter", key="compare_food_2")

    if st.button("Compare Products", type="primary"):
        if not food1.strip() or not food2.strip():
            st.warning("Enter both product names before comparing.")
        elif food1.strip().casefold() == food2.strip().casefold():
            st.warning("Enter two different products to compare.")
        else:
            with st.spinner("Searching Open Food Facts for both products..."):
                try:
                    product1 = search_open_food_facts(food1)
                    product2 = search_open_food_facts(food2)
                    if not product1:
                        st.error(f'No matching product was found for "{food1}". Try a more specific product or brand name.')
                    elif not product2:
                        st.error(f'No matching product was found for "{food2}". Try a more specific product or brand name.')
                    else:
                        st.success("Both products were found in Open Food Facts.")
                        compare_col1, compare_col2 = st.columns(2)
                        with compare_col1:
                            nutrition1 = show_comparison_product(product1, "Product 1")
                        with compare_col2:
                            nutrition2 = show_comparison_product(product2, "Product 2")

                        st.markdown("### Side-by-side nutrition comparison")
                        comparison_items = [
                            ("Calories", "energy-kcal_100g", "kcal", "lower"),
                            ("Total fat", "fat_100g", "g", "lower"),
                            ("Saturated fat", "saturated-fat_100g", "g", "lower"),
                            ("Carbohydrates", "carbohydrates_100g", "g", "context"),
                            ("Sugars", "sugars_100g", "g", "lower"),
                            ("Fiber", "fiber_100g", "g", "higher"),
                            ("Protein", "proteins_100g", "g", "higher"),
                            ("Salt", "salt_100g", "g", "lower"),
                        ]
                        header1, header2 = st.columns(2)
                        header1.markdown(f"**{product1.get('product_name') or product1.get('product_name_en') or 'Product 1'}**")
                        header2.markdown(f"**{product2.get('product_name') or product2.get('product_name_en') or 'Product 2'}**")
                        for title, key, unit, direction in comparison_items:
                            value1 = nutrition1.get(key)
                            value2 = nutrition2.get(key)
                            left, right = st.columns(2)
                            def format_value(value):
                                if value is None:
                                    return "Not provided"
                                try:
                                    return f"{float(value):g} {unit} / 100 g"
                                except (TypeError, ValueError):
                                    return f"{value} {unit} / 100 g"
                            left.write(f"**{title}:** {format_value(value1)}")
                            right.write(f"**{title}:** {format_value(value2)}")
                            if value1 is not None and value2 is not None:
                                try:
                                    difference = float(value1) - float(value2)
                                    st.caption(f"Difference (Product 1 − Product 2): {difference:+g} {unit} per 100 g")
                                except (TypeError, ValueError):
                                    pass

                        st.caption("Nutrition values are shown per 100 g for a like-for-like comparison. A lower or higher value is not automatically better for every nutrient; consider serving size and your dietary needs.")

                        # Automatic plain-language summary of four commonly compared nutrients.
                        st.markdown("### 🧾 Comparison Summary")
                        summary_metrics = [
                            ("Calories", "energy-kcal_100g", "kcal", "lower"),
                            ("Sugar", "sugars_100g", "g", "lower"),
                            ("Saturated fat", "saturated-fat_100g", "g", "lower"),
                            ("Protein", "proteins_100g", "g", "higher"),
                        ]
                        wins = {"Product 1": 0, "Product 2": 0}
                        available_comparisons = 0
                        for metric_name, metric_key, metric_unit, preferred in summary_metrics:
                            raw1 = nutrition1.get(metric_key)
                            raw2 = nutrition2.get(metric_key)
                            try:
                                number1 = float(raw1) if raw1 is not None else None
                                number2 = float(raw2) if raw2 is not None else None
                            except (TypeError, ValueError):
                                number1 = number2 = None

                            if number1 is None or number2 is None:
                                st.write(f"**{metric_name}:** Cannot compare — data missing for one or both products.")
                                continue

                            available_comparisons += 1
                            if number1 == number2:
                                st.write(f"**{metric_name}:** Tie — both contain {number1:g} {metric_unit} per 100 g.")
                            else:
                                product1_is_better = number1 < number2 if preferred == "lower" else number1 > number2
                                winner = "Product 1" if product1_is_better else "Product 2"
                                wins[winner] += 1
                                better_value = min(number1, number2) if preferred == "lower" else max(number1, number2)
                                other_value = max(number1, number2) if preferred == "lower" else min(number1, number2)
                                st.write(
                                    f"**{metric_name}:** {winner} has the more favorable value "
                                    f"({better_value:g} vs. {other_value:g} {metric_unit} per 100 g)."
                                )

                        st.markdown("#### Overall takeaway")
                        if available_comparisons == 0:
                            st.warning("There is not enough nutrition data to generate a comparison summary.")
                        elif wins["Product 1"] > wins["Product 2"]:
                            st.success(f"{product1.get('product_name') or 'Product 1'} has more favorable results across these available indicators ({wins['Product 1']} vs. {wins['Product 2']}).")
                        elif wins["Product 2"] > wins["Product 1"]:
                            st.success(f"{product2.get('product_name') or 'Product 2'} has more favorable results across these available indicators ({wins['Product 2']} vs. {wins['Product 1']}).")
                        else:
                            st.info("The products are tied across the available indicators, or neither has more favorable results overall.")
                        st.caption("This takeaway compares only calories, sugar, saturated fat, and protein when data is available. It is not a medical or personalized dietary recommendation. Check serving sizes and the package label; a product is not automatically healthier based on these four values alone.")
                except (RuntimeError, ValueError) as exc:
                    st.error(str(exc))

    st.caption("Data source: Open Food Facts. Product records are community-contributed and may be incomplete or outdated. Verify nutrition information on the package label.")

elif st.session_state.page == "Food Diary":
    st.title("📔 My Food Diary")
    meal = st.text_input("What did you eat?")
    meal_type = st.selectbox("Meal type", ["Breakfast","Lunch","Dinner","Snack"])
    if st.button("Save Meal"):
        if meal.strip():
            st.session_state.diary.append({"food":meal.strip(),"type":meal_type})
            st.success("Meal added for this session.")
            st.rerun()
        else:
            st.warning("Enter a food name.")
    st.divider()
    st.subheader("Your Meals")
    if st.session_state.diary:
        for item in st.session_state.diary:
            st.write(f"🍽️ {item['type']}: {item['food']}")
    else:
        st.info("Your diary is currently empty. Entries are not permanently saved yet.")

elif st.session_state.page == "Nutrition Calendar":
    st.title("📅 Nutrition Calendar")
    st.write("Track your daily meals and nutrition activity.")

    import pandas as pd
    from datetime import date

    if "calendar_entries" not in st.session_state:
        st.session_state.calendar_entries = []

    st.subheader("Add a Meal")

    meal_date = st.date_input("Meal date", value=date.today())
    meal_type = st.selectbox(
        "Meal type",
        ["Breakfast", "Lunch", "Dinner", "Snack"]
    )
    food_name = st.text_input("Food name")
    notes = st.text_input("Notes (optional)")

    if st.button("Save Meal to Calendar"):
        if food_name.strip():
            st.session_state.calendar_entries.append({
                "Date": str(meal_date),
                "Meal": meal_type,
                "Food": food_name.strip(),
                "Notes": notes
            })
            st.success("Meal added to your calendar!")
        else:
            st.warning("Please enter a food name.")

    st.divider()
    st.subheader("Your Nutrition Calendar")

    if st.session_state.calendar_entries:
        entries = sorted(
            st.session_state.calendar_entries,
            key=lambda x: x["Date"],
            reverse=True
        )
        st.dataframe(entries, use_container_width=True)

        if st.button("Clear Calendar"):
           st.session_state.calendar_entries = []
           st.rerun()

    else:
        st.info("No meals recorded yet. Add your first meal above.")

    st.caption("Calendar entries are stored temporarily during this session.")

elif st.session_state.page == "Recent Scans":
    st.title("🔍 Recent Scans")
    st.write("Your recently scanned food products.")

    if "scan_history" not in st.session_state:
        st.session_state.scan_history = []

    if st.session_state.scan_history:
        st.subheader("Scan History")
        
        for item in reversed(st.session_state.scan_history):
            with st.container():
                st.write(f"### {item.get('name', 'Unknown product')}")
                st.write(f"**Barcode:** {item.get('barcode', 'N/A')}")
                st.divider()

        if st.button("Clear Scan History"):
            st.session_state.scan_history = []
            st.success("Scan history cleared!")
            st.rerun()

    else:
        st.info("No scanned products yet. Scan a food product to see it here.")

    st.caption("Scan history is stored temporarily during this session.")
    
elif st.session_state.page == "AI Nutrition Assistant":
    st.title("🤖 RecallMatch AI Nutrition Assistant")
    st.write(
        "Your personal food and nutrition assistant. "
        "Ask questions about food, ingredients and nutrition."
    )

    # Get the latest scanned product
    product = st.session_state.get("last_product", None)

    # Get saved account preferences
    profile = st.session_state.get("account_profile", {})
    diet = profile.get("diet", "No specific diet")
    allergies = profile.get("allergies", "")
    st.subheader("Your Nutrition Profile")
    st.write(f"**Dietary preference:** {diet}")
    st.write(f"**Food allergies:** {allergies or 'Not specified'}")
    
    st.divider()

    st.subheader("Latest Scanned Product")

    if product and isinstance(product, dict):
        product_name = product.get("product_name") or product.get("name", "Unknown product")
        nutriments = product.get("nutriments", {})

        if not isinstance(nutriments, dict):
            nutriments = {}

        st.write(f"**Product:** {product_name}")

        calories = nutriments.get("energy-kcal_100g")
        sugar = nutriments.get("sugars_100g")
        protein = nutriments.get("proteins_100g")
        fat = nutriments.get("fat_100g")
        saturated_fat = nutriments.get("saturated-fat_100g")

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric(
                "Calories / 100g",
                f"{calories} kcal" if calories is not None else "N/A"
            )

        with col2:
            st.metric(
                "Sugar / 100g",
                f"{sugar} g" if sugar is not None else "N/A"
            )

        with col3:
            st.metric(
                "Protein / 100g",
                f"{protein} g" if protein is not None else "N/A"
            )

        if fat is not None:
            st.write(f"**Total fat:** {fat} g per 100g")

        if saturated_fat is not None:
            st.write(f"**Saturated fat:** {saturated_fat} g per 100g")

    else:
        st.info(
            "No product scanned yet. Use Food Scanner first "
            "to get personalized product information."
        )
        product_name = None
        nutriments = {}
        sugar = None
        protein = None
        calories = None
        fat = None
        saturated_fat = None

    st.divider()

    st.subheader("Ask RecallMatch")

    question = st.text_input(
        "What would you like to know?",
        placeholder="Example: Is this product high in sugar?"
    )

    if st.button("Ask Nutrition Assistant"):
        if not question.strip():
            st.warning("Please enter a question.")
        else:
            q = question.lower()
            answer = ""
            if any(word in q for word in ["allerg", "peanut", "milk", "soy", "gluten"]):
                if allergies:
                    answer = (
                        f"Your profile lists these food allergies: {allergies}. "
                        "Check the product ingredients and allergen label carefully. "
                        "The scanner may not detect every allergen."
                    )

                else:
                    answer = (
                        "You have not listed any food allergies in My Account. "
                        "Always check the package label for allergen information."
                    )

            elif any(word in q for word in ["sugar", "sweet"]):
                if sugar is not None:
                    try:
                        value = float(sugar)
                        if value >= 22.5:
                            level = "high"
                        elif value <= 5:
                            level = "low"
                        else:
                            level = "moderate"
                            
                        answer = (
                            f"{product_name} contains {value} g of sugar per 100 g. "
                            f"This is considered a {level} amount using general "
                            "nutrition-label guidelines."
                        )

                    except (ValueError, TypeError):
                        answer = "Sugar information is not available in a usable format."
                else:
                    answer = "Scan a product with available sugar information first."

            elif any(word in q for word in ["protein", "muscle"]):
                if protein is not None:
                    answer = (
                        f"{product_name} contains {protein} g of protein per 100 g. "
                        "Protein is important for muscle maintenance and body functions."
                    )

                else:
                    answer = "Protein information is not available for this product."

            elif any(word in q for word in ["calorie", "energy", "kcal"]):
                if calories is not None:
                    answer = (
                        f"{product_name} contains {calories} kcal per 100 g. "
                        "Remember that your portion size affects the calories consumed."
                    )

                else:
                    answer = "Calorie information is not available for this product."

            elif any(word in q for word in ["fat", "saturated"]):
                if fat is not None:
                    answer = (
                        f"{product_name} contains {fat} g of total fat per 100 g. "
                    )

                    if saturated_fat is not None:
                        answer += f"It also contains {saturated_fat} g of saturated fat."

                else:
                    answer = "Fat information is not available for this product."

            elif any(word in q for word in ["healthy", "good for me", "good food"]):
                if product and sugar is not None and protein is not None:
                    answer = (
                        f"Here is a basic nutrition overview of {product_name}: "
                        f"{sugar} g sugar and {protein} g protein per 100 g. "
                        "Consider the serving size, ingredients and your dietary needs. "
                        "This information alone cannot determine whether a food is healthy."
                    )

                else:
                    answer = (
                        "To evaluate a food, consider its calories, sugar, saturated fat, "
                        "protein, fiber, ingredients and serving size."
                    )

            elif any(word in q for word in ["diet", "vegetarian", "vegan", "gluten"]):
                answer = (
                    f"Your saved dietary preference is {diet}. "
                    "Check the ingredient list and product certification to verify "
                    "whether a product meets your dietary requirements."
                )

            else:
                answer = (
                    "I can help with questions about sugar, protein, calories, fat, "
                    "allergens and dietary preferences. Try asking one of these topics."
                )

            st.markdown("### 💡 RecallMatch Recommendation")
            st.info(answer)

            st.caption(
                "This assistant uses basic rules and available product data. "
                "It does not provide medical advice or guarantee allergen safety."
            )

    st.divider()

    st.subheader("Suggested Questions")

    examples = [
        "Is this product high in sugar?",
        "How much protein does it contain?",
        "How many calories does it have?",
        "Does my profile list any allergies?",
        "Is this product suitable for my diet?"
    ]

    for example in examples:
        st.write(f"• {example}")

    st.caption("RecallMatch 2.0 | Food Intelligence Platform")    
    
elif st.session_state.page == "My Account":
    st.title("👤 My Account")
    st.write("Manage your RecallMatch profile.")

    if "account_profile" not in st.session_state:
        st.session_state.account_profile = {
            "name": "",
            "diet": "No specific diet",
            "allergies": ""
        }

    profile = st.session_state.account_profile

    st.subheader("Personal Information")

    name = st.text_input(
        "Your name",
        value=profile.get("name", ""),
        key="account_name"
    )

    diet_options = [
        "No specific diet",
        "Vegetarian",
        "Vegan",
        "Gluten-free",
        "Dairy-free",
        "Low-sugar"
    ]

    current_diet = profile.get("diet", "No specific diet")

    if current_diet not in diet_options:
        current_diet = "No specific diet"

    diet = st.selectbox(
        "Dietary preference",
        diet_options,
        index=diet_options.index(current_diet),
        key="account_diet"
    )

    allergies = st.text_input(
        "Food allergies",
        value=profile.get("allergies", ""),
        placeholder="Example: peanuts, milk, soy",
        key="account_allergies"
    )

    if st.button("Save Profile"):
        st.session_state.account_profile = {
            "name": name,
            "diet": diet,
            "allergies": allergies
        }
        st.success("Profile saved successfully!")

    st.divider()
    st.subheader("Your Saved Profile")

    saved_profile = st.session_state.account_profile

    st.write("**Name:**", saved_profile["name"])
    st.write("**Diet:**", saved_profile["diet"])
    st.write("**Food allergies:**", saved_profile["allergies"])

    st.caption("Profile information is stored temporarily in this session.")
st.caption("RecallMatch 2.0 | Food Intelligence Platform")
