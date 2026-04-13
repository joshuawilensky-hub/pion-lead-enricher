"""
Pion Restaurant Lead Enricher - Web App
Streamlit interface for finding and enriching restaurant leads.
"""

import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime
from typing import List, Optional
import urllib.parse

# Page config
st.set_page_config(
    page_title="Pion Lead Enricher",
    page_icon="🎯",
    layout="wide"
)

# Lead sources
LEAD_SOURCES = {
    "qsr": {
        "name": "QSR Magazine Top 50",
        "description": "Top quick-service restaurants by sales",
        "query": "QSR Magazine Top 50 quick service restaurants 2024 2025 list ranking"
    },
    "fastcasual": {
        "name": "Fast Casual Top 100",
        "description": "Top fast casual restaurants",
        "query": "Fast Casual Top 100 restaurants 2024 2025 Movers Shakers list"
    },
    "unidays": {
        "name": "UNiDAYS Partners",
        "description": "Competitors - restaurants on UNiDAYS",
        "query": "UNiDAYS food drink restaurant partners student discount USA 2024 2025"
    },
    "sheerid": {
        "name": "SheerID Clients",
        "description": "Competitors - restaurants using SheerID",
        "query": "SheerID restaurant food clients case studies student verification"
    },
    "eagleeye": {
        "name": "Eagle Eye Clients",
        "description": "Promo-ready brands (warm leads)",
        "query": "Eagle Eye Solutions restaurant hospitality clients partners"
    },
    "genzcampus": {
        "name": "Campus Chains",
        "description": "Popular near college campuses",
        "query": "most popular restaurants near college campus Gen Z 2024 2025 chains"
    }
}

SYSTEM_PROMPT = """You are a deep-research assistant for Pion (formerly Student Beans), a B2B sales tool helping Business Development Managers identify and qualify US restaurant brands as sales leads.

Pion sells student verification and marketing products to restaurant chains. Your job is to research each brand thoroughly and return a structured JSON object.

For each restaurant brand, search the web and return ONLY this JSON object with no other text:
{
    "brand": "Brand Name",
    "website": "official website URL",
    "segment": "QSR or Fast Casual or Casual Dining or Pizza or Coffee/Bakery or Other",
    "us_location_count": "estimated number e.g. 500, or range e.g. 200-300, or Unknown",
    "us_presence": "Yes or No or Limited or Unclear",

    "has_student_discount": "Yes or No or Unclear",
    "student_discount_details": "describe the offer e.g. 10% off with UNiDAYS, in-store only - or None if not found",
    "student_discount_provider": "UNiDAYS or SheerID or ID.me or Student Beans or Pion or None or Unclear",

    "has_loyalty_app": "Yes or No or Unclear",
    "loyalty_app_name": "name of app e.g. Chipotle Rewards, MyPanera - or None",
    "loyalty_is_strategic_priority": "Yes or No or Unclear - look for press releases, app download pushes, loyalty programme marketing",

    "runs_general_promos": "Yes or No or Unclear",
    "promo_examples": "list up to 3 specific examples e.g. BOGO Tuesdays, app-exclusive 20% off, seasonal deals - or None",
    "promo_channels": "list which apply: App / Website / In-store / Email / Social",

    "pion_product_fit": "one of: Verification / Loyalty-SSO / BeansID / Media / Multiple / None",
    "pion_tier": "Tier 1 or Tier 2 or Tier 3 or Skip",
    "tier_rationale": "one sentence explaining why this tier was assigned",

    "recommended_contact_title": "best title to reach out to e.g. VP Marketing, Head of Loyalty, CMO, Director of Digital",
    "linkedin_search_url": "https://www.linkedin.com/search/results/people/?keywords=BRAND%20VP%20Marketing%20Head%20of%20Loyalty",
    "notes": "any other useful context for a sales rep"
}

Tier logic - assign tiers as follows:
- Tier 1: Brand uses UNiDAYS, SheerID, or ID.me for student verification AND has 50+ US locations. This is a displacement opportunity - Pion can replace the competitor.
- Tier 1: Brand has an active loyalty app that is a strategic priority AND already runs a student discount. This is a Loyalty SSO (Playbook 3) opportunity.
- Tier 2: Brand has 50+ US locations AND runs general promotions (promo-native) but has no student discount yet. Greenfield Verification + Media opportunity.
- Tier 2: Brand has a loyalty app but no student discount programme. Entry point for Loyalty SSO pitch.
- Tier 3: Brand has US presence but limited promo activity and no student discount. Needs more nurture.
- Skip: Fewer than 50 US locations, or no meaningful US presence, or already on Student Beans or Pion.

Product fit logic:
- If they use a competitor verification platform -> pion_product_fit = Verification
- If they have a loyalty app as a priority -> pion_product_fit = Loyalty-SSO
- If they already have student verification and want to expand to other groups (graduates, military, healthcare) -> pion_product_fit = BeansID
- If they are a large brand with no verification but run heavy promotions -> pion_product_fit = Multiple (Verification + Media)

Return ONLY the JSON object. No markdown, no explanation, no code fences."""


PITCH_SYSTEM_PROMPT = """You are a senior B2B sales strategist for Pion (formerly Student Beans). Pion sells student verification and marketing products to restaurant chains.

Pion's product suite:
- Verification: Gated student discounts verified by Pion (replaces UNiDAYS, SheerID, ID.me)
- Loyalty-SSO: Integrates student verification into a brand's existing loyalty app via single sign-on
- BeansID: Extends verification beyond students to graduates, NHS/healthcare workers, military, teachers
- Media: Sponsored placements on Student Beans platform reaching 22M+ verified students

You will be given enriched data for a restaurant brand. Based on this data, return ONLY this JSON object with no other text:
{
    "primary_product": "the single best Pion product to lead with",
    "secondary_product": "second product to mention or upsell to, or null",
    "pitch_angle": "one sentence framing the core value proposition for this specific brand",
    "talking_points": [
        "Talking point 1 - specific, data-driven, references their actual situation",
        "Talking point 2 - specific, data-driven, references their actual situation",
        "Talking point 3 - specific, data-driven, references their actual situation"
    ],
    "competitor_displacement": "if they use UNiDAYS/SheerID/ID.me, write a one-sentence displacement argument. Otherwise null.",
    "objection_handling": {
        "objection": "most likely objection this brand will raise",
        "response": "how to handle it"
    },
    "email_subject": "a compelling cold outreach subject line (max 8 words)",
    "opening_line": "a personalised first sentence for a cold email that references something specific about this brand"
}

Return ONLY the JSON object. No markdown, no explanation, no code fences."""


CONTACTS_SYSTEM_PROMPT = """You are a B2B sales researcher for Pion (formerly Student Beans), which sells student marketing and verification products to restaurant chains.

You will be given a restaurant brand name and context about which Pion products are relevant. Your job is to find 3-5 real decision makers, stakeholders, and champions at this brand who would be involved in buying or championing a student discount / loyalty / marketing programme.

Target roles to find (in priority order):
1. VP/Director of Marketing or Brand
2. Head of Loyalty / Director of Digital / VP CRM
3. CMO or Chief Digital Officer
4. VP/Director of Partnerships or Business Development  
5. Marketing Manager (if large brand, skip; if mid-size, include)

For each contact, search LinkedIn and the web to find real people currently in these roles. Do not invent names.

Return ONLY this JSON array with no other text:
[
    {
        "name": "Full Name or Unknown if not found",
        "title": "their actual title",
        "role_type": "Decision Maker or Stakeholder or Champion",
        "why_relevant": "one sentence on why they'd care about Pion",
        "linkedin_url": "https://www.linkedin.com/in/their-profile or null if not found",
        "linkedin_search_url": "https://www.linkedin.com/search/results/people/?keywords=BRAND+TITLE",
        "confidence": "High or Medium or Low"
    }
]

Role type definitions:
- Decision Maker: Has budget authority and can sign off on a deal
- Stakeholder: Will be involved in the decision or implementation
- Champion: Would benefit from this internally and could advocate for it

Return ONLY the JSON array. No markdown, no explanation, no code fences."""


def get_client(provider: str, api_key: str):
    """Get API client for provider."""
    if provider == "anthropic":
        from anthropic import Anthropic
        return Anthropic(api_key=api_key)
    elif provider == "perplexity":
        from openai import OpenAI
        return OpenAI(api_key=api_key, base_url="https://api.perplexity.ai")
    elif provider == "openai":
        from openai import OpenAI
        return OpenAI(api_key=api_key)
    return None


def call_llm(provider: str, api_key: str, system: str, user: str, use_search: bool = True) -> str:
    """Unified LLM call across providers. Returns raw text."""
    if provider == "anthropic":
        from anthropic import Anthropic
        client = Anthropic(api_key=api_key)
        kwargs = dict(
            model="claude-sonnet-4-20250514",
            max_tokens=2048,
            system=system,
            messages=[{"role": "user", "content": user}]
        )
        if use_search:
            kwargs["tools"] = [{"type": "web_search_20250305", "name": "web_search"}]
        message = client.messages.create(**kwargs)
        return "".join(block.text for block in message.content if hasattr(block, "text"))

    elif provider == "perplexity":
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url="https://api.perplexity.ai")
        response = client.chat.completions.create(
            model="sonar",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ]
        )
        return response.choices[0].message.content

    elif provider == "openai":
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ]
        )
        return response.choices[0].message.content

    return ""


def parse_json_object(text: str) -> dict:
    start = text.find('{')
    end = text.rfind('}') + 1
    if start >= 0 and end > start:
        return json.loads(text[start:end])
    return {}


def parse_json_array(text: str) -> list:
    start = text.find('[')
    end = text.rfind(']') + 1
    if start >= 0 and end > start:
        return json.loads(text[start:end])
    return []


def search_leads(provider: str, api_key: str, source_key: str, exclude: List[str] = None) -> List[str]:
    """Search for restaurant brands from a source, excluding already-known brands."""
    source = LEAD_SOURCES[source_key]
    exclude = exclude or []

    exclusion_block = ""
    if exclude:
        # Send up to 200 known brands to keep the prompt lean
        sample = exclude[:200]
        exclusion_block = f"""
IMPORTANT: The following brands are already in our database. Do NOT include them in your results — return only brands we don't have yet:
{json.dumps(sample)}
"""

    prompt = f"""Search for: {source['query']}

Find restaurant brand names. Return ONLY a JSON array of brand names:
["McDonald's", "Chipotle", "Panera Bread"]

Focus on US restaurant chains. Return at least 20 brands that are NOT in the exclusion list below. Dig deeper than the obvious top brands — include regional chains, emerging chains, and brands ranked 20-100 in the relevant lists. Just the JSON array.
{exclusion_block}"""

    try:
        if provider == "anthropic":
            from anthropic import Anthropic
            client = Anthropic(api_key=api_key)
            message = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2048,
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
                messages=[{"role": "user", "content": prompt}]
            )
            text = "".join(block.text for block in message.content if hasattr(block, "text"))
        elif provider == "perplexity":
            from openai import OpenAI
            client = OpenAI(api_key=api_key, base_url="https://api.perplexity.ai")
            response = client.chat.completions.create(
                model="sonar",
                messages=[{"role": "user", "content": prompt}]
            )
            text = response.choices[0].message.content
        elif provider == "openai":
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}]
            )
            text = response.choices[0].message.content
        else:
            return []

        return parse_json_array(text)

    except Exception as e:
        st.error(f"Error searching leads: {e}")
        return []


def enrich_brand(provider: str, api_key: str, brand: str) -> dict:
    """Enrich a single brand."""
    prompt = f'Research "{brand}" restaurant chain. Return only the JSON object as specified.'
    try:
        text = call_llm(provider, api_key, SYSTEM_PROMPT, prompt, use_search=True)
        return parse_json_object(text) or {"brand": brand, "pion_tier": "Error", "notes": "Failed to parse"}
    except Exception as e:
        st.error(f"Error enriching {brand}: {e}")
        return {"brand": brand, "pion_tier": "Error", "notes": str(e)}


def generate_pitch(provider: str, api_key: str, enriched_data: dict) -> dict:
    """Generate pitch recommendation for an enriched brand."""
    brand = enriched_data.get("brand", "Unknown")
    prompt = f"""Here is the enriched research data for {brand}:

{json.dumps(enriched_data, indent=2)}

Based on this data, generate the pitch strategy JSON object."""

    try:
        text = call_llm(provider, api_key, PITCH_SYSTEM_PROMPT, prompt, use_search=False)
        return parse_json_object(text) or {}
    except Exception as e:
        st.error(f"Error generating pitch for {brand}: {e}")
        return {}


def find_contacts(provider: str, api_key: str, brand: str, product_fit: str, segment: str) -> list:
    """Find key contacts at a brand."""
    prompt = f"""Brand: {brand}
Segment: {segment}
Relevant Pion products: {product_fit}

Find 3-5 real decision makers and stakeholders at {brand} who would be relevant for selling a student discount / loyalty / marketing programme. Search LinkedIn and the web."""

    try:
        text = call_llm(provider, api_key, CONTACTS_SYSTEM_PROMPT, prompt, use_search=True)
        return parse_json_array(text) or []
    except Exception as e:
        st.error(f"Error finding contacts for {brand}: {e}")
        return []


def generate_linkedin_url(brand: str) -> str:
    query = f"{brand} VP Marketing Director Marketing CMO Head of Loyalty"
    return f"https://www.linkedin.com/search/results/people/?keywords={urllib.parse.quote(query)}"


def highlight_tier(val):
    colors = {
        'Tier 1': 'background-color: #90EE90',
        'Tier 2': 'background-color: #FFE4B5',
        'Tier 3': 'background-color: #D3D3D3',
        'Skip': 'background-color: #FFB6C1',
        'Error': 'background-color: #FFB6C1'
    }
    return colors.get(val, '')


def render_pitch_card(pitch: dict, brand: str):
    """Render a styled pitch recommendation card."""
    if not pitch:
        st.warning("No pitch data available.")
        return

    primary = pitch.get("primary_product", "")
    secondary = pitch.get("secondary_product")
    angle = pitch.get("pitch_angle", "")
    talking_points = pitch.get("talking_points", [])
    competitor = pitch.get("competitor_displacement")
    objection = pitch.get("objection_handling", {})
    subject = pitch.get("email_subject", "")
    opener = pitch.get("opening_line", "")

    product_colors = {
        "Verification": "#2563EB",
        "Loyalty-SSO": "#7C3AED",
        "BeansID": "#059669",
        "Media": "#D97706",
        "Multiple": "#DC2626",
    }
    primary_color = product_colors.get(primary, "#6B7280")

    st.markdown(f"""
    <div style="
        border: 2px solid {primary_color};
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 16px;
        background: linear-gradient(135deg, {primary_color}08 0%, transparent 60%);
    ">
        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 12px;">
            <span style="
                background: {primary_color};
                color: white;
                padding: 4px 12px;
                border-radius: 20px;
                font-size: 13px;
                font-weight: 700;
                letter-spacing: 0.5px;
            ">LEAD WITH: {primary}</span>
            {"<span style='background: #F3F4F6; color: #374151; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600;'>+ " + secondary + "</span>" if secondary else ""}
        </div>
        <p style="font-size: 15px; font-style: italic; color: #1F2937; margin: 0; line-height: 1.5;">
            "{angle}"
        </p>
    </div>
    """, unsafe_allow_html=True)

    col_l, col_r = st.columns(2)

    with col_l:
        st.markdown("**🎯 Talking Points**")
        for i, tp in enumerate(talking_points, 1):
            st.markdown(f"""
            <div style="
                background: #F8FAFC;
                border-left: 3px solid {primary_color};
                padding: 10px 14px;
                margin-bottom: 8px;
                border-radius: 0 8px 8px 0;
                font-size: 14px;
                color: #374151;
            ">
                <strong style="color: {primary_color};">{i}.</strong> {tp}
            </div>
            """, unsafe_allow_html=True)

        if competitor:
            st.markdown("**⚔️ Displacement Argument**")
            st.markdown(f"""
            <div style="
                background: #FEF3C7;
                border: 1px solid #F59E0B;
                padding: 10px 14px;
                border-radius: 8px;
                font-size: 14px;
                color: #92400E;
            ">{competitor}</div>
            """, unsafe_allow_html=True)

    with col_r:
        if objection:
            st.markdown("**🛡️ Handle the Objection**")
            st.markdown(f"""
            <div style="background: #FEF2F2; border: 1px solid #FCA5A5; padding: 10px 14px; border-radius: 8px; margin-bottom: 10px;">
                <p style="font-size: 13px; color: #991B1B; margin: 0 0 6px 0;">
                    <strong>They'll say:</strong> "{objection.get('objection', '')}"
                </p>
                <p style="font-size: 13px; color: #1F2937; margin: 0;">
                    <strong>You say:</strong> {objection.get('response', '')}
                </p>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("**✉️ Cold Email Opener**")
        st.markdown(f"""
        <div style="background: #F0FDF4; border: 1px solid #86EFAC; padding: 12px 14px; border-radius: 8px;">
            <p style="font-size: 12px; color: #166534; margin: 0 0 6px 0;">
                <strong>Subject:</strong> {subject}
            </p>
            <p style="font-size: 13px; color: #1F2937; margin: 0; line-height: 1.5;">
                {opener}
            </p>
        </div>
        """, unsafe_allow_html=True)


def render_contacts_table(contacts: list, brand: str):
    """Render contacts in a structured card layout."""
    if not contacts:
        st.info("No contacts found. Try running contact discovery.")
        return

    role_colors = {
        "Decision Maker": ("#DC2626", "#FEF2F2"),
        "Stakeholder": ("#2563EB", "#EFF6FF"),
        "Champion": ("#059669", "#ECFDF5"),
    }
    confidence_icons = {"High": "🟢", "Medium": "🟡", "Low": "🔴"}

    cols = st.columns(min(len(contacts), 3))
    for i, contact in enumerate(contacts):
        col_idx = i % 3
        role = contact.get("role_type", "Stakeholder")
        accent, bg = role_colors.get(role, ("#6B7280", "#F9FAFB"))
        conf = contact.get("confidence", "Medium")
        name = contact.get("name", "Unknown")
        title = contact.get("title", "")
        why = contact.get("why_relevant", "")
        li_url = contact.get("linkedin_url") or contact.get("linkedin_search_url", "")

        with cols[col_idx]:
            st.markdown(f"""
            <div style="
                background: {bg};
                border: 1.5px solid {accent}40;
                border-top: 3px solid {accent};
                border-radius: 10px;
                padding: 14px;
                margin-bottom: 12px;
                min-height: 160px;
            ">
                <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px;">
                    <span style="
                        background: {accent};
                        color: white;
                        font-size: 10px;
                        font-weight: 700;
                        padding: 2px 8px;
                        border-radius: 10px;
                        letter-spacing: 0.5px;
                    ">{role.upper()}</span>
                    <span style="font-size: 12px;">{confidence_icons.get(conf, '🟡')} {conf}</span>
                </div>
                <p style="font-size: 15px; font-weight: 700; color: #111827; margin: 0 0 2px 0;">{name}</p>
                <p style="font-size: 12px; color: #6B7280; margin: 0 0 8px 0;">{title}</p>
                <p style="font-size: 12px; color: #374151; margin: 0 0 10px 0; line-height: 1.4;">{why}</p>
                {"<a href='" + li_url + "' target='_blank' style='font-size: 12px; color: #2563EB; text-decoration: none; font-weight: 600;'>🔗 View LinkedIn →</a>" if li_url else ""}
            </div>
            """, unsafe_allow_html=True)


# ── Sidebar ────────────────────────────────────────────────────────────────────
st.sidebar.title("⚙️ Settings")

provider = st.sidebar.selectbox(
    "Provider",
    ["perplexity", "anthropic", "openai"],
    help="Perplexity is cheapest ($0.005/lead). Anthropic gives best quality."
)

default_key = ""
if provider == "perplexity":
    default_key = st.secrets.get("PERPLEXITY_API_KEY", os.environ.get("PERPLEXITY_API_KEY", ""))
elif provider == "anthropic":
    default_key = st.secrets.get("ANTHROPIC_API_KEY", os.environ.get("ANTHROPIC_API_KEY", ""))
elif provider == "openai":
    default_key = st.secrets.get("OPENAI_API_KEY", os.environ.get("OPENAI_API_KEY", ""))

api_key = st.sidebar.text_input(
    "API Key",
    value=default_key,
    type="password",
    help="Your API key for the selected provider"
)

cost_per_lead = {"perplexity": 0.005, "anthropic": 0.015, "openai": 0.025}
st.sidebar.caption(f"~${cost_per_lead[provider]:.3f} per lead enrichment")
st.sidebar.caption(f"~${cost_per_lead[provider] * 2:.3f} per lead with pitch + contacts")
st.sidebar.markdown("---")
db_size = len(st.session_state.get('brand_database', []))
st.sidebar.caption(f"📦 Database: {db_size} brands")
if db_size > 0:
    if st.sidebar.button("🗑️ Clear database", help="Reset brand database for a fresh start"):
        st.session_state['brand_database'] = []
        st.session_state['found_leads'] = []
        st.rerun()
st.sidebar.markdown("---")
st.sidebar.caption("Built for Pion BD - US Restaurant Vertical")

# ── Main ───────────────────────────────────────────────────────────────────────
st.title("🎯 Pion Restaurant Lead Enricher")
st.caption("Find, research, and build pitch strategies for restaurant brands")

tab1, tab2, tab3, tab4 = st.tabs(["🔍 Find Leads", "📊 Enrich Leads", "🚀 Validate & Pitch", "📁 My Results"])

# ── Initialise master brand database in session state ──────────────────────────
if 'brand_database' not in st.session_state:
    st.session_state['brand_database'] = []  # cumulative list across all runs

def normalise(name: str) -> str:
    """Lowercase + strip for dedup comparison."""
    return name.strip().lower()

def merge_into_database(new_brands: List[str]) -> tuple:
    """Add new brands to master database, return (added, already_known)."""
    existing_normalised = {normalise(b) for b in st.session_state['brand_database']}
    added, dupes = [], []
    for b in new_brands:
        if normalise(b) not in existing_normalised:
            st.session_state['brand_database'].append(b)
            existing_normalised.add(normalise(b))
            added.append(b)
        else:
            dupes.append(b)
    return added, dupes

# ── Tab 1: Find Leads ──────────────────────────────────────────────────────────
with tab1:
    st.header("Find Restaurant Leads")

    # ── Database status bar ────────────────────────────────────────────────────
    db = st.session_state['brand_database']
    db_col1, db_col2, db_col3 = st.columns([2, 2, 3])
    db_col1.metric("📦 Brands in database", len(db))
    db_col2.metric("🆕 New this session", len([b for b in db if b in st.session_state.get('found_leads', [])]))

    with db_col3:
        if db:
            db_csv = pd.DataFrame({"Brand": db}).to_csv(index=False)
            st.download_button(
                "📥 Export full database",
                db_csv,
                f"pion_brand_database_{datetime.now().strftime('%Y%m%d')}.csv",
                "text/csv",
                help="Download all brands discovered so far"
            )

    # ── Seed database from CSV ─────────────────────────────────────────────────
    with st.expander("📂 Seed database from existing CSV (optional)", expanded=not bool(db)):
        st.caption("Upload a CSV of brands you've already found to prevent duplicates on future runs.")
        seed_file = st.file_uploader("Upload existing brand list", type=["csv"], key="seed_uploader")
        if seed_file:
            seed_df = pd.read_csv(seed_file)
            seed_col = next(
                (c for c in seed_df.columns if c.lower() in ['brand', 'name', 'company', 'restaurant']),
                seed_df.columns[0]
            )
            seed_brands = seed_df[seed_col].dropna().astype(str).tolist()
            added, _ = merge_into_database(seed_brands)
            st.success(f"✅ Seeded {len(added)} new brands into database ({len(seed_brands) - len(added)} already present)")

    st.markdown("---")
    st.write("Select sources to search for new brands:")

    col1, col2 = st.columns(2)
    selected_sources = []

    with col1:
        st.subheader("Industry Lists")
        if st.checkbox("QSR Top 50", help="Top quick-service by sales"):
            selected_sources.append("qsr")
        if st.checkbox("Fast Casual Top 100", help="Growth brands"):
            selected_sources.append("fastcasual")
        if st.checkbox("Campus Chains", help="Popular near colleges"):
            selected_sources.append("genzcampus")

    with col2:
        st.subheader("Competitor Intel")
        if st.checkbox("UNiDAYS Partners", help="🎯 High priority - competitor customers"):
            selected_sources.append("unidays")
        if st.checkbox("SheerID Clients", help="🎯 High priority - competitor customers"):
            selected_sources.append("sheerid")
        if st.checkbox("Eagle Eye Clients", help="Promo-ready brands"):
            selected_sources.append("eagleeye")

    if db:
        st.info(f"🔒 Exclusion active — the {len(db)} brands already in your database will be excluded from results, surfacing only new brands.")

    if st.button("🔍 Find New Leads", type="primary", disabled=not api_key or not selected_sources):
        all_brands = []
        progress = st.progress(0)
        status = st.empty()

        # Pass full database as exclusion list to every source query
        known_brands = list(st.session_state['brand_database'])

        for i, source_key in enumerate(selected_sources):
            status.write(f"Searching {LEAD_SOURCES[source_key]['name']} (excluding {len(known_brands)} known brands)...")
            brands = search_leads(provider, api_key, source_key, exclude=known_brands)
            all_brands.extend(brands)
            # Update known list mid-run so each subsequent source also excludes
            # brands found in earlier sources this run
            known_brands = list(dict.fromkeys(known_brands + brands))
            progress.progress((i + 1) / len(selected_sources))

        # Merge into master database
        added, dupes = merge_into_database(all_brands)
        status.write(f"✅ Found **{len(added)} new** brands | {len(dupes)} already in database | {len(st.session_state['brand_database'])} total")

        st.session_state['found_leads'] = added  # only surface new ones for enrichment

        if added:
            st.success(f"🆕 {len(added)} new brands added to database")
            st.dataframe(pd.DataFrame({"Brand": added}), use_container_width=True)

            csv = pd.DataFrame({"Brand": added}).to_csv(index=False)
            st.download_button(
                "📥 Download new leads CSV",
                csv,
                f"new_leads_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                "text/csv"
            )
        else:
            st.warning("No new brands found — all results were already in your database. Try different sources or check back later as lists update.")

        if dupes:
            with st.expander(f"ℹ️ {len(dupes)} duplicates skipped"):
                st.write(", ".join(dupes))

# ── Tab 2: Enrich Leads ────────────────────────────────────────────────────────
with tab2:
    st.header("Enrich Leads")

    input_method = st.radio(
        "Input method",
        ["Use found leads", "Paste brand names", "Upload CSV"],
        horizontal=True
    )

    brands_to_enrich = []

    if input_method == "Use found leads":
        if 'found_leads' in st.session_state and st.session_state['found_leads']:
            brands_to_enrich = st.session_state['found_leads']
            st.write(f"Ready to enrich {len(brands_to_enrich)} brands")
        else:
            st.info("No leads found yet. Go to 'Find Leads' tab first, or paste/upload brands.")

    elif input_method == "Paste brand names":
        text_input = st.text_area(
            "Brand names (one per line)",
            placeholder="Sweetgreen\nChipotle\nShake Shack",
            height=150
        )
        if text_input:
            brands_to_enrich = [b.strip() for b in text_input.split('\n') if b.strip()]
            st.write(f"{len(brands_to_enrich)} brands entered")

    elif input_method == "Upload CSV":
        uploaded = st.file_uploader("Upload CSV", type=['csv'])
        if uploaded:
            df_upload = pd.read_csv(uploaded)
            brand_col = None
            for col in df_upload.columns:
                if col.lower() in ['brand', 'name', 'company', 'restaurant']:
                    brand_col = col
                    break
            if brand_col is None:
                brand_col = df_upload.columns[0]
            brands_to_enrich = df_upload[brand_col].dropna().tolist()
            st.write(f"{len(brands_to_enrich)} brands loaded from '{brand_col}' column")

    if brands_to_enrich:
        est_cost = len(brands_to_enrich) * cost_per_lead[provider]
        st.caption(f"Estimated cost: ${est_cost:.2f}")

    if st.button("📊 Enrich Leads", type="primary", disabled=not api_key or not brands_to_enrich):
        results = []
        progress = st.progress(0)
        status = st.empty()

        for i, brand in enumerate(brands_to_enrich):
            status.write(f"Researching {brand}...")
            result = enrich_brand(provider, api_key, brand)
            result['linkedin_search'] = generate_linkedin_url(brand)
            results.append(result)
            progress.progress((i + 1) / len(brands_to_enrich))

        status.write(f"✅ Enriched {len(results)} brands")
        st.session_state['enriched_results'] = results

        df = pd.DataFrame(results)

        if 'pion_tier' in df.columns:
            styled = df.style.map(highlight_tier, subset=['pion_tier'])
        else:
            styled = df

        st.dataframe(
            styled,
            use_container_width=True,
            column_config={
                "linkedin_search_url": st.column_config.LinkColumn("LinkedIn"),
                "linkedin_search": st.column_config.LinkColumn("LinkedIn Search"),
                "website": st.column_config.LinkColumn("Website"),
            }
        )

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("🥇 Tier 1", len([r for r in results if r.get('pion_tier') == 'Tier 1']))
        col2.metric("🥈 Tier 2", len([r for r in results if r.get('pion_tier') == 'Tier 2']))
        col3.metric("🥉 Tier 3", len([r for r in results if r.get('pion_tier') == 'Tier 3']))
        col4.metric("⏭️ Skip", len([r for r in results if r.get('pion_tier') == 'Skip']))

        csv = df.to_csv(index=False)
        st.download_button(
            "📥 Download Results CSV",
            csv,
            f"pion_leads_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            "text/csv"
        )

# ── Tab 3: Validate & Pitch ────────────────────────────────────────────────────
with tab3:
    st.header("🚀 Validate & Pitch")
    st.caption("Generate pitch strategies and find key contacts for specific brands")

    # Brand selector
    enriched = st.session_state.get('enriched_results', [])
    enriched_brand_names = [r.get('brand', '') for r in enriched if r.get('brand')]

    input_mode = st.radio(
        "Select brand",
        ["Pick from enriched results", "Enter brand name manually"],
        horizontal=True
    )

    selected_brand_data = {}
    manual_brand = ""

    if input_mode == "Pick from enriched results":
        if enriched_brand_names:
            selected_brand_name = st.selectbox("Choose a brand", enriched_brand_names)
            selected_brand_data = next(
                (r for r in enriched if r.get('brand') == selected_brand_name), {}
            )
            if selected_brand_data:
                tier = selected_brand_data.get('pion_tier', 'Unknown')
                fit = selected_brand_data.get('pion_product_fit', 'Unknown')
                segment = selected_brand_data.get('segment', 'Unknown')
                locations = selected_brand_data.get('us_location_count', 'Unknown')
                tier_colors = {'Tier 1': '🟢', 'Tier 2': '🟡', 'Tier 3': '🟠', 'Skip': '🔴'}
                st.markdown(f"""
                **{tier_colors.get(tier, '⚪')} {tier}** &nbsp;|&nbsp;
                **Product Fit:** {fit} &nbsp;|&nbsp;
                **Segment:** {segment} &nbsp;|&nbsp;
                **US Locations:** {locations}
                """)
        else:
            st.info("No enriched results yet. Enrich brands in the 'Enrich Leads' tab first, or use manual entry.")

    else:
        manual_brand = st.text_input("Brand name", placeholder="e.g. Shake Shack")
        if manual_brand:
            selected_brand_data = {"brand": manual_brand}

    active_brand = selected_brand_data.get("brand", manual_brand)

    if active_brand:
        st.markdown("---")

        col_pitch, col_contacts = st.columns(2)

        run_pitch = col_pitch.button(
            "🎯 Generate Pitch Strategy",
            type="primary",
            disabled=not api_key,
            help="Generates talking points, email opener, and objection handling"
        )
        run_contacts = col_contacts.button(
            "👥 Find Key Contacts",
            disabled=not api_key,
            help="Searches for real decision makers, stakeholders and champions"
        )

        run_both = st.button(
            "⚡ Run Both (Pitch + Contacts)",
            disabled=not api_key,
            type="secondary"
        )

        # Cached pitch/contacts in session state
        cache_key_pitch = f"pitch_{active_brand}"
        cache_key_contacts = f"contacts_{active_brand}"

        if run_pitch or run_both:
            with st.spinner(f"Generating pitch strategy for {active_brand}..."):
                # If we don't have full enriched data, enrich first
                if len(selected_brand_data) <= 1:
                    st.info(f"Enriching {active_brand} first...")
                    selected_brand_data = enrich_brand(provider, api_key, active_brand)
                    # Store back
                    if 'enriched_results' not in st.session_state:
                        st.session_state['enriched_results'] = []
                    st.session_state['enriched_results'].append(selected_brand_data)

                pitch = generate_pitch(provider, api_key, selected_brand_data)
                st.session_state[cache_key_pitch] = pitch

        if run_contacts or run_both:
            with st.spinner(f"Finding contacts at {active_brand}..."):
                product_fit = selected_brand_data.get("pion_product_fit", "Multiple")
                segment = selected_brand_data.get("segment", "Restaurant")
                contacts = find_contacts(provider, api_key, active_brand, product_fit, segment)
                st.session_state[cache_key_contacts] = contacts

        # Display results
        if cache_key_pitch in st.session_state or cache_key_contacts in st.session_state:
            st.markdown(f"## {active_brand}")

            if cache_key_pitch in st.session_state:
                st.markdown("### 🎯 Pitch Strategy")
                render_pitch_card(st.session_state[cache_key_pitch], active_brand)

            if cache_key_contacts in st.session_state:
                st.markdown("### 👥 Key Contacts")
                render_contacts_table(st.session_state[cache_key_contacts], active_brand)

                # Export contacts
                contacts_data = st.session_state[cache_key_contacts]
                if contacts_data:
                    df_contacts = pd.DataFrame(contacts_data)
                    df_contacts.insert(0, "brand", active_brand)
                    st.download_button(
                        "📥 Export Contacts CSV",
                        df_contacts.to_csv(index=False),
                        f"contacts_{active_brand.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.csv",
                        "text/csv"
                    )

        # Batch pitch generation for all Tier 1/2 brands
        st.markdown("---")
        st.subheader("📦 Batch Pitch Generation")
        st.caption("Generate pitch strategies for all Tier 1 and Tier 2 brands at once")

        tier_12 = [r for r in enriched if r.get('pion_tier') in ('Tier 1', 'Tier 2')]
        if tier_12:
            st.write(f"{len(tier_12)} Tier 1/2 brands ready for batch processing")
            batch_mode = st.radio(
                "Include contacts?",
                ["Pitch only (faster)", "Pitch + Contacts (thorough)"],
                horizontal=True
            )
            if st.button(f"⚡ Batch Generate for {len(tier_12)} brands", disabled=not api_key):
                batch_progress = st.progress(0)
                batch_status = st.empty()
                batch_results = []

                for i, brand_data in enumerate(tier_12):
                    bname = brand_data.get("brand", "")
                    batch_status.write(f"Processing {bname} ({i+1}/{len(tier_12)})...")

                    pitch = generate_pitch(provider, api_key, brand_data)
                    st.session_state[f"pitch_{bname}"] = pitch

                    contacts = []
                    if "Contacts" in batch_mode:
                        contacts = find_contacts(
                            provider, api_key, bname,
                            brand_data.get("pion_product_fit", "Multiple"),
                            brand_data.get("segment", "Restaurant")
                        )
                        st.session_state[f"contacts_{bname}"] = contacts

                    batch_results.append({
                        "brand": bname,
                        "tier": brand_data.get("pion_tier"),
                        "product_fit": brand_data.get("pion_product_fit"),
                        "primary_product": pitch.get("primary_product", ""),
                        "pitch_angle": pitch.get("pitch_angle", ""),
                        "talking_point_1": pitch.get("talking_points", [""])[0] if pitch.get("talking_points") else "",
                        "talking_point_2": pitch.get("talking_points", ["", ""])[1] if len(pitch.get("talking_points", [])) > 1 else "",
                        "talking_point_3": pitch.get("talking_points", ["", "", ""])[2] if len(pitch.get("talking_points", [])) > 2 else "",
                        "email_subject": pitch.get("email_subject", ""),
                        "opening_line": pitch.get("opening_line", ""),
                        "objection": pitch.get("objection_handling", {}).get("objection", ""),
                        "objection_response": pitch.get("objection_handling", {}).get("response", ""),
                        "top_contact": contacts[0].get("name", "") if contacts else "",
                        "top_contact_title": contacts[0].get("title", "") if contacts else "",
                        "top_contact_linkedin": contacts[0].get("linkedin_url") or contacts[0].get("linkedin_search_url", "") if contacts else "",
                    })
                    batch_progress.progress((i + 1) / len(tier_12))

                batch_status.write(f"✅ Batch complete — {len(batch_results)} brands processed")
                df_batch = pd.DataFrame(batch_results)
                st.dataframe(df_batch, use_container_width=True)
                st.download_button(
                    "📥 Download Batch Results",
                    df_batch.to_csv(index=False),
                    f"pion_pitches_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    "text/csv"
                )
        else:
            st.info("No Tier 1 or Tier 2 brands in results yet. Enrich leads first.")

# ── Tab 4: My Results ──────────────────────────────────────────────────────────
with tab4:
    st.header("My Results")

    if 'enriched_results' in st.session_state and st.session_state['enriched_results']:
        results = st.session_state['enriched_results']
        df = pd.DataFrame(results)

        col1, col2 = st.columns(2)
        with col1:
            tier_filter = st.multiselect(
                "Filter by Tier",
                ['Tier 1', 'Tier 2', 'Tier 3', 'Skip'],
                default=['Tier 1', 'Tier 2']
            )
        with col2:
            fit_options = df['pion_product_fit'].unique().tolist() if 'pion_product_fit' in df.columns else []
            fit_filter = st.multiselect("Filter by Product Fit", fit_options)

        filtered = df[df['pion_tier'].isin(tier_filter)] if tier_filter and 'pion_tier' in df.columns else df
        if fit_filter and 'pion_product_fit' in df.columns:
            filtered = filtered[filtered['pion_product_fit'].isin(fit_filter)]

        st.dataframe(
            filtered,
            use_container_width=True,
            column_config={
                "linkedin_search_url": st.column_config.LinkColumn("LinkedIn"),
                "linkedin_search": st.column_config.LinkColumn("LinkedIn Search"),
                "website": st.column_config.LinkColumn("Website")
            }
        )

        # Tier 1 call list with pitch previews
        tier1 = [r for r in results if r.get('pion_tier') == 'Tier 1']
        if tier1:
            st.subheader("🎯 Tier 1 Priority Call List")
            st.caption("Top targets — act on these first. Click a brand to view pitch strategy.")
            for r in tier1:
                bname = r['brand']
                linkedin = r.get('linkedin_search_url') or r.get('linkedin_search', '')
                pitch_cached = st.session_state.get(f"pitch_{bname}")
                contacts_cached = st.session_state.get(f"contacts_{bname}")

                with st.expander(f"**{bname}** — {r.get('pion_product_fit', '')} | {r.get('student_discount_provider', '')}"):
                    st.caption(r.get('tier_rationale', r.get('notes', '')))

                    if pitch_cached:
                        st.markdown("**Pitch Angle:** " + pitch_cached.get("pitch_angle", ""))
                        st.markdown("**Lead with:** " + pitch_cached.get("primary_product", ""))
                    else:
                        st.caption("No pitch generated yet — go to Validate & Pitch tab")

                    if contacts_cached:
                        st.markdown(f"**{len(contacts_cached)} contacts found**")
                        for c in contacts_cached[:2]:
                            li = c.get("linkedin_url") or c.get("linkedin_search_url", "")
                            st.markdown(f"• {c.get('name')} — {c.get('title')} [{c.get('role_type')}]({li})")
                    else:
                        st.markdown(f"[🔍 Search LinkedIn]({linkedin})")

        csv = df.to_csv(index=False)
        st.download_button(
            "📥 Download All Results CSV",
            csv,
            f"pion_leads_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            "text/csv"
        )
    else:
        st.info("No results yet. Go to 'Enrich Leads' tab to get started.")
