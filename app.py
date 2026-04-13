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

SYSTEM_PROMPT = """You are a research assistant for Pion (formerly Student Beans), a student verification platform.

For each restaurant brand, return a JSON object:
{
    "brand": "Brand Name",
    "website": "URL",
    "us_presence": "Yes/No/Limited/Unclear",
    "has_student_discount": "Yes/No/Unclear",
    "discount_url": "URL if found",
    "verification_provider": "Student Beans/Pion/UNiDAYS/SheerID/ID.me/None",
    "priority": "High/Medium/Low/Already Partner",
    "notes": "Brief notes"
}

Priority: High = competitor verification, Medium = US presence no discount, Already Partner = on Student Beans/Pion, Low = no US presence"""


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
            
        elif provider == "gemini":
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            # Tools parameter completely removed for stability
            llm = genai.GenerativeModel(model_name="gemini-1.5-pro")
            response = llm.generate_content(prompt)
            text = response.text
        
        # Parse JSON
        start = text.find('[')
        end = text.rfind(']') + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
    except Exception as e:
        st.error(f"Error: {e}")
    
    return []


def enrich_brand(provider: str, api_key: str, brand: str) -> dict:
    """Enrich a single brand."""
    prompt = f'Research "{brand}" restaurant for student discount status. Return only JSON with: brand, website, us_presence, has_student_discount, discount_url, verification_provider, priority, notes'
    
    try:
        if provider == "anthropic":
            client = get_client(provider, api_key)
            message = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1024,
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
            
        elif provider == "gemini":
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            # Tools parameter completely removed for stability
            llm = genai.GenerativeModel(
                model_name="gemini-1.5-pro",
                system_instruction=SYSTEM_PROMPT
            )
            response = llm.generate_content(prompt)
            text = response.text
        
        # Parse JSON
        start = text.find('{')
        end = text.rfind('}') + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
    
    except Exception as e:
        st.error(f"Error enriching {brand}: {e}")
    
    return {"brand": brand, "priority": "Error", "notes": "Failed to enrich"}


def generate_linkedin_url(brand: str) -> str:
    """Generate LinkedIn search URL."""
    query = f"{brand} VP Marketing Director Marketing CMO Head of Partnerships"
    return f"https://www.linkedin.com/search/results/people/?keywords={urllib.parse.quote(query)}"


# Sidebar - API Configuration
st.sidebar.title("⚙️ Settings")

provider = st.sidebar.selectbox(
    "Provider",
    ["perplexity", "anthropic", "openai", "gemini"],
    help="Perplexity is cheapest ($0.005/lead). Gemini includes Google Search."
)

# Try to get API key from secrets first, then show input
default_key = ""
if provider == "perplexity":
    default_key = st.secrets.get("PERPLEXITY_API_KEY", os.environ.get("PERPLEXITY_API_KEY", ""))
elif provider == "anthropic":
    default_key = st.secrets.get("ANTHROPIC_API_KEY", os.environ.get("ANTHROPIC_API_KEY", ""))
elif provider == "openai":
    default_key = st.secrets.get("OPENAI_API_KEY", os.environ.get("OPENAI_API_KEY", ""))
elif provider == "gemini":
    default_key = st.secrets.get("GEMINI_API_KEY", os.environ.get("GEMINI_API_KEY", ""))

api_key = st.sidebar.text_input(
    "API Key",
    value=default_key,
    type="password",
    help="Your API key for the selected provider"
)

cost_per_lead = {"perplexity": 0.005, "anthropic": 0.015, "openai": 0.025, "gemini": 0.010}
st.sidebar.caption(f"~${cost_per_lead[provider]:.3f} per lead")

# Main content
st.title("🎯 Pion Restaurant Lead Enricher")
st.caption("Find and research restaurant brands for student discount opportunities")

# Tabs
tab1, tab2, tab3 = st.tabs(["🔍 Find Leads", "📊 Enrich Leads", "📁 My Results"])

# Tab 1: Find Leads
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
        
        # Deduplicate
        unique_brands = list(dict.fromkeys(all_brands))
        
        status.write(f"✅ Found {len(unique_brands)} unique brands")
        
        # Store in session state
        st.session_state['found_leads'] = unique_brands
        
        # Display
        st.dataframe(pd.DataFrame({"Brand": unique_brands}), use_container_width=True)
        
        # Download button
        csv = pd.DataFrame({"Brand": unique_brands}).to_csv(index=False)
        st.download_button(
            "📥 Download CSV",
            csv,
            f"leads_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            "text/csv"
        )

# Tab 2: Enrich Leads
with tab2:
    st.header("Enrich Leads")
    
    # Input options
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
            df = pd.read_csv(uploaded)
            # Try to find brand column
            brand_col = None
            for col in df.columns:
                if col.lower() in ['brand', 'name', 'company', 'restaurant']:
                    brand_col = col
                    break
            if brand_col is None:
                brand_col = df.columns[0]
            
            brands_to_enrich = df[brand_col].dropna().tolist()
            st.write(f"{len(brands_to_enrich)} brands loaded from '{brand_col}' column")
    
    # Estimate cost
    if brands_to_enrich:
        est_cost = len(brands_to_enrich) * cost_per_lead[provider]
        st.caption(f"Estimated cost: ${est_cost:.2f}")
    
    # Enrich button
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
        
        # Store results
        st.session_state['enriched_results'] = results
        
        # Create DataFrame
        df = pd.DataFrame(results)
        
        # Color code priority
        def highlight_priority(val):
            colors = {
                'High': 'background-color: #90EE90',
                'Medium': 'background-color: #FFE4B5',
                'Already Partner': 'background-color: #ADD8E6',
                'Low': 'background-color: #D3D3D3',
                'Error': 'background-color: #FFB6C1'
            }
            return colors.get(val, '')
        
        # Display
        st.dataframe(
            df.style.applymap(highlight_priority, subset=['priority']),
            use_container_width=True,
            column_config={
                "linkedin_search": st.column_config.LinkColumn("LinkedIn"),
                "website": st.column_config.LinkColumn("Website"),
                "discount_url": st.column_config.LinkColumn("Discount URL")
            }
        )
        
        # Summary
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("🎯 High", len([r for r in results if r.get('priority') == 'High']))
        col2.metric("📊 Medium", len([r for r in results if r.get('priority') == 'Medium']))
        col3.metric("✅ Already Partner", len([r for r in results if r.get('priority') == 'Already Partner']))
        col4.metric("⬇️ Low", len([r for r in results if r.get('priority') == 'Low']))
        
        # Download
        csv = df.to_csv(index=False)
        st.download_button(
            "📥 Download Results CSV",
            csv,
            f"pion_leads_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            "text/csv"
        )

# Tab 3: Results
with tab3:
    st.header("My Results")
    
    if 'enriched_results' in st.session_state and st.session_state['enriched_results']:
        results = st.session_state['enriched_results']
        df = pd.DataFrame(results)
        
        # Filters
        col1, col2 = st.columns(2)
        with col1:
            priority_filter = st.multiselect(
                "Filter by Priority",
                ['High', 'Medium', 'Already Partner', 'Low'],
                default=['High', 'Medium']
            )
        with col2:
            provider_filter = st.multiselect(
                "Filter by Verification Provider",
                df['verification_provider'].unique().tolist() if 'verification_provider' in df.columns else []
            )
        
        # Apply filters
        filtered = df[df['priority'].isin(priority_filter)] if priority_filter else df
        if provider_filter:
            filtered = filtered[filtered['verification_provider'].isin(provider_filter)]
        
        st.dataframe(
            filtered,
            use_container_width=True,
            column_config={
                "linkedin_search": st.column_config.LinkColumn("LinkedIn"),
                "website": st.column_config.LinkColumn("Website")
            }
        )
        
        # High priority call list
        high_priority = [r for r in results if r.get('priority') == 'High']
        if high_priority:
            st.subheader("🎯 High Priority Call List")
            st.write("These brands use competitor verification - best conversion targets:")
            for r in high_priority:
                st.write(f"**{r['brand']}** - {r.get('verification_provider', 'Unknown')} → [LinkedIn]({r.get('linkedin_search', '')})")
                st.caption(r.get('notes', ''))
    else:
        st.info("No results yet. Go to 'Enrich Leads' tab to get started.")

# Footer
st.sidebar.markdown("---")
st.sidebar.caption("Built for Pion BD - US Restaurant Vertical")
