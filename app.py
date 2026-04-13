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


def search_leads(provider: str, api_key: str, source_key: str) -> List[str]:
    """Search for restaurant brands from a source."""
    source = LEAD_SOURCES[source_key]

    prompt = f"""Search for: {source['query']}

Find restaurant brand names. Return ONLY a JSON array of brand names:
["McDonald's", "Chipotle", "Panera Bread"]

Focus on US restaurant chains. Return at least 20 brands. Just the JSON array."""

    try:
        if provider == "anthropic":
            client = get_client(provider, api_key)
            message = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2048,
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
                messages=[{"role": "user", "content": prompt}]
            )
            text = "".join(block.text for block in message.content if hasattr(block, 'text'))

        elif provider == "perplexity":
            client = get_client(provider, api_key)
            response = client.chat.completions.create(
                model="sonar",
                messages=[{"role": "user", "content": prompt}]
            )
            text = response.choices[0].message.content

        elif provider == "openai":
            client = get_client(provider, api_key)
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}]
            )
            text = response.choices[0].message.content

        else:
            return []

        # Parse JSON array
        start = text.find('[')
        end = text.rfind(']') + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])

    except Exception as e:
        st.error(f"Error searching leads: {e}")

    return []


def enrich_brand(provider: str, api_key: str, brand: str) -> dict:
    """Enrich a single brand."""
    prompt = f'Research "{brand}" restaurant chain. Return only the JSON object as specified.'

    try:
        if provider == "anthropic":
            client = get_client(provider, api_key)
            message = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2048,
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}]
            )
            text = "".join(block.text for block in message.content if hasattr(block, 'text'))

        elif provider == "perplexity":
            client = get_client(provider, api_key)
            response = client.chat.completions.create(
                model="sonar",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ]
            )
            text = response.choices[0].message.content

        elif provider == "openai":
            client = get_client(provider, api_key)
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ]
            )
            text = response.choices[0].message.content

        else:
            return {"brand": brand, "pion_tier": "Error", "notes": "Unsupported provider"}

        # Parse JSON object
        start = text.find('{')
        end = text.rfind('}') + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])

    except Exception as e:
        st.error(f"Error enriching {brand}: {e}")

    return {"brand": brand, "pion_tier": "Error", "notes": "Failed to enrich"}


def generate_linkedin_url(brand: str) -> str:
    """Generate LinkedIn search URL."""
    query = f"{brand} VP Marketing Director Marketing CMO Head of Loyalty"
    return f"https://www.linkedin.com/search/results/people/?keywords={urllib.parse.quote(query)}"


def highlight_tier(val):
    """Color code pion_tier column."""
    colors = {
        'Tier 1': 'background-color: #90EE90',
        'Tier 2': 'background-color: #FFE4B5',
        'Tier 3': 'background-color: #D3D3D3',
        'Skip': 'background-color: #FFB6C1',
        'Error': 'background-color: #FFB6C1'
    }
    return colors.get(val, '')


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
st.sidebar.caption(f"~${cost_per_lead[provider]:.3f} per lead")
st.sidebar.markdown("---")
st.sidebar.caption("Built for Pion BD - US Restaurant Vertical")

# ── Main ───────────────────────────────────────────────────────────────────────
st.title("🎯 Pion Restaurant Lead Enricher")
st.caption("Find and research restaurant brands for student discount opportunities")

tab1, tab2, tab3 = st.tabs(["🔍 Find Leads", "📊 Enrich Leads", "📁 My Results"])

# ── Tab 1: Find Leads ──────────────────────────────────────────────────────────
with tab1:
    st.header("Find Restaurant Leads")
    st.write("Select sources to build your prospect list:")

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

    if st.button("🔍 Find Leads", type="primary", disabled=not api_key or not selected_sources):
        all_brands = []
        progress = st.progress(0)
        status = st.empty()

        for i, source_key in enumerate(selected_sources):
            status.write(f"Searching {LEAD_SOURCES[source_key]['name']}...")
            brands = search_leads(provider, api_key, source_key)
            all_brands.extend(brands)
            progress.progress((i + 1) / len(selected_sources))

        unique_brands = list(dict.fromkeys(all_brands))
        status.write(f"✅ Found {len(unique_brands)} unique brands")
        st.session_state['found_leads'] = unique_brands

        st.dataframe(pd.DataFrame({"Brand": unique_brands}), use_container_width=True)

        csv = pd.DataFrame({"Brand": unique_brands}).to_csv(index=False)
        st.download_button(
            "📥 Download CSV",
            csv,
            f"leads_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            "text/csv"
        )

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

        # Display with tier colour coding if column exists
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
                "discount_url": st.column_config.LinkColumn("Discount URL")
            }
        )

        # Summary metrics
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

# ── Tab 3: My Results ──────────────────────────────────────────────────────────
with tab3:
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

        # Tier 1 call list
        tier1 = [r for r in results if r.get('pion_tier') == 'Tier 1']
        if tier1:
            st.subheader("🎯 Tier 1 Call List")
            st.write("Top targets — act on these first:")
            for r in tier1:
                linkedin = r.get('linkedin_search_url') or r.get('linkedin_search', '')
                st.write(f"**{r['brand']}** — {r.get('pion_product_fit', '')} | {r.get('student_discount_provider', '')} → [LinkedIn]({linkedin})")
                st.caption(r.get('tier_rationale', r.get('notes', '')))
    else:
        st.info("No results yet. Go to 'Enrich Leads' tab to get started.")
