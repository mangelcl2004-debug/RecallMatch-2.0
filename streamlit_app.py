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


PAGES = ["Home", "Food Scanner", "FDA Recalls", "Compare Foods",
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
    col1,col2 = st.columns(2)
    with col1:
        st.subheader("Product 1")
        food1 = st.text_input("First food product")
    with col2:
        st.subheader("Product 2")
        food2 = st.text_input("Second food product")
    if st.button("Compare Products"):
        st.info("Product comparison will be connected after product lookup is tested.")

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
    st.write("Your nutrition activity calendar.")
    st.info("Calendar tracking will be implemented in a future phase.")

elif st.session_state.page == "Recent Scans":
    st.title("🕘 Recent Scans")
    st.info("Scan history and permanent storage will be implemented in a future phase.")

elif st.session_state.page == "AI Nutrition Assistant":
    st.title("🤖 RecallMatch AI")
    st.write("Your food and nutrition assistant.")
    question = st.text_input("Ask a nutrition question")
    if st.button("Send") and question.strip():
        st.info("The AI service has not been connected yet.")

elif st.session_state.page == "My Account":
    st.title("👤 My Account")
    st.write("Manage your RecallMatch profile.")
    st.info("Secure registration and authentication will be implemented in a future phase.")

st.divider()
st.caption("RecallMatch 2.0 | Food Intelligence Platform")
