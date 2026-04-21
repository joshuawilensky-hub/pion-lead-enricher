"""
Pion Restaurant Lead Enricher
Four-step workflow: Find → Research → Contacts → Pitch
Multi-Provider with Gemini, Anthropic, Perplexity, OpenAI
"""

import streamlit as st
import pandas as pd
import json
import os
import time
import re
from datetime import datetime
from typing import List, Optional, Dict
import urllib.parse

st.set_page_config(page_title="Pion Lead Enricher", page_icon="🎓", layout="wide")

# ══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════
LEAD_SOURCES = {
    "general": {
        "name": "General Restaurant Search",
        "description": "Broad search for US restaurant brands with student-age appeal",
        "query": "popular US restaurant chains fast casual dining brands 2024 2025"
    },
    "fast_growing": {
        "name": "Fastest Growing Chains",
        "description": "Restaurant brands expanding rapidly — more likely to invest in marketing",
        "query": "fastest growing restaurant chains US 2024 2025 expansion new locations"
    },
    "student_friendly": {
        "name": "Student-Friendly Brands",
        "description": "Brands already targeting Gen Z / college demographics",
        "query": "restaurant brands popular with college students Gen Z dining 2024 2025"
    },
    "loyalty_programs": {
        "name": "Brands with Loyalty / Rewards",
        "description": "Restaurants with existing loyalty programs — may be open to student offers",
        "query": "restaurant chains loyalty programs rewards apps discounts 2024 2025"
    },
}

SEGMENTS = {
    "fast_casual": "Fast Casual",
    "qsr": "QSR (Quick Service)",
    "casual_dining": "Casual Dining",
    "coffee_beverage": "Coffee & Beverage",
    "pizza": "Pizza",
    "healthy_bowls": "Healthy / Bowls",
    "bakery_dessert": "Bakery & Dessert",
}

PERSONAS = {
    "marketing_leader": {
        "label": "Marketing Leader",
        "description": "Owns student/loyalty programs. Cares about customer acquisition cost, brand affinity with Gen Z.",
        "titles": ["VP of Marketing", "CMO", "Director of Marketing", "Head of Brand Marketing"],
    },
    "partnerships_bd": {
        "label": "Partnerships / BD",
        "description": "Manages third-party deals. Cares about incremental traffic, partnership ROI.",
        "titles": ["VP of Partnerships", "Director of Business Development", "Head of Strategic Partnerships"],
    },
    "digital_loyalty": {
        "label": "Digital / Loyalty Owner",
        "description": "Runs the app, loyalty program, and digital offers. Cares about redemption rates, app engagement.",
        "titles": ["VP of Digital", "Director of Loyalty", "Head of CRM", "Director of Digital Marketing"],
    },
}

# ── System Prompts ────────────────────────────────────────────────────────────

FIND_SYSTEM_PROMPT = """Find US restaurant brands matching the given criteria. Return ONLY a JSON array:
[{"company":"Brand Name","website":"URL","us_locations":"number or range or Unknown","segment":"Fast Casual/QSR/Casual Dining/Coffee & Beverage/Pizza/Healthy & Bowls/Bakery & Dessert/Other","student_appeal":"High/Medium/Low - brief reason"}]
No markdown, no explanation, just the JSON array."""


RESEARCH_SYSTEM_PROMPT = """Research a restaurant brand's student discount status and marketing posture. Return ONLY this JSON:
{"company":"Name","website":"URL","us_presence":true/false,"us_locations":"number or estimate","has_student_discount":true/false,"discount_details":"describe the discount or None","discount_url":"URL to student discount page or empty","verification_provider":"Student Beans/UNiDAYS/SheerID/ID.me/In-house/None","loyalty_program":"describe or None","app_available":true/false,"social_media_presence":"strong/moderate/weak","gen_z_marketing":"describe any Gen Z targeting or None","competitor_discounts":"which competitors offer student discounts","priority":"High/Medium/Low/Already Partner","priority_rationale":"one sentence","notes":"anything else useful"}

Priority logic:
- High: Uses a competitor verification provider (Student Beans, UNiDAYS, SheerID) — pitch Pion as better value and better student reach
- Medium: US presence, no student discount yet — greenfield opportunity
- Already Partner: Already uses Pion or is on Student Beans — skip or upsell
- Low: No US presence or tiny brand
No markdown, just JSON."""


CONTACTS_SYSTEM_PROMPT = """Find contacts at a restaurant brand matching requested personas. Return ONLY a JSON array:
[{"company":"Name","name":"Full Name or Not Found","title":"Job title","persona":"Marketing Leader/Partnerships & BD/Digital & Loyalty Owner","seniority":"C-Suite/VP/Director/Head/Manager","why_relevant":"one sentence","linkedin_search_url":"LinkedIn search URL","confidence":"High/Medium/Low"}]

Personas: Marketing Leader=CMO/VP Marketing/Director Marketing. Partnerships & BD=VP Partnerships/Director BD. Digital & Loyalty=VP Digital/Director Loyalty/Head CRM.
Search for real people. If name not found, set "Not Found" but still provide title and LinkedIn URL. No markdown, just JSON."""


PITCH_SYSTEM_PROMPT = """Generate a personalized sales pitch for Pion. Pion is a student discount and loyalty platform that helps restaurant brands reach millions of verified students. Pion verifies student status and drives incremental foot traffic and online orders.

Key selling points:
- Access to millions of verified students across the US and UK
- Higher redemption rates than competitors like Student Beans or UNiDAYS
- Simple integration (no POS changes required for online)
- Pay-per-redemption model — no upfront costs
- Gen Z brand affinity — students become lifelong customers
- Data & insights on student spending behavior

Return ONLY this JSON:
{"company":"Name","contact_name":"Name","contact_title":"Title","persona":"Persona","email_subject":"max 8 words","opening_line":"personalized first sentence","pitch_angle":"one sentence value prop","talking_points":["1","2","3"],"estimated_impact":"potential student traffic / revenue uplift estimate","objection":"likely objection","objection_response":"how to handle","call_to_action":"next step"}
No markdown, just JSON."""


# ══════════════════════════════════════════════════════════════════════════════
# API & HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _get_secret(key: str) -> Optional[str]:
    """Read from st.secrets with env-var fallback."""
    try:
        return st.secrets[key]
    except Exception:
        return os.environ.get(key, "")


def call_llm(provider, api_key, system, user, use_search=True):
    if provider == "anthropic":
        from anthropic import Anthropic
        client = Anthropic(api_key=api_key)
        kwargs = dict(model="claude-sonnet-4-5", max_tokens=4096, system=system,
                      messages=[{"role": "user", "content": user}])
        if use_search:
            kwargs["tools"] = [{"type": "web_search_20250305", "name": "web_search"}]
        msg = client.messages.create(**kwargs)
        return "".join(b.text for b in msg.content if hasattr(b, "text"))
    elif provider == "gemini":
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=api_key)
        tools = []
        if use_search:
            tools.append(types.Tool(google_search=types.GoogleSearch()))
        config = types.GenerateContentConfig(
            system_instruction=system,
            tools=tools if tools else None,
        )
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=user,
            config=config,
        )
        if response.text:
            return response.text
        try:
            parts = response.candidates[0].content.parts
            return "".join(p.text for p in parts if hasattr(p, "text") and p.text) or ""
        except Exception:
            return ""
    elif provider == "perplexity":
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url="https://api.perplexity.ai")
        r = client.chat.completions.create(model="sonar",
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
        return r.choices[0].message.content
    elif provider == "openai":
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        r = client.chat.completions.create(model="gpt-4o",
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
        return r.choices[0].message.content
    return ""


def _clean_llm_text(text: str) -> str:
    """Strip markdown code fences and common LLM wrapper junk."""
    if not text:
        return ""
    text = re.sub(r'```(?:json|JSON)?\s*', '', text)
    text = text.replace('```', '')
    return text.strip()


def parse_json_array(text):
    text = _clean_llm_text(text)
    if not text:
        st.caption("⚠️ LLM returned empty response — try again or switch providers.")
        return []
    s, e = text.find('['), text.rfind(']') + 1
    if s >= 0 and e > s:
        try:
            return json.loads(text[s:e])
        except json.JSONDecodeError as ex:
            st.caption(f"⚠️ JSON parse error: {ex}. Raw snippet: {text[s:s+200]}...")
    else:
        st.caption(f"⚠️ No JSON array found in response. Raw snippet: {text[:300]}...")
    return []


def parse_json_object(text):
    text = _clean_llm_text(text)
    if not text:
        return {}
    s, e = text.find('{'), text.rfind('}') + 1
    if s >= 0 and e > s:
        try:
            return json.loads(text[s:e])
        except json.JSONDecodeError:
            st.caption(f"⚠️ JSON parse error. Raw snippet: {text[s:s+200]}...")
    return {}


def li_url(company, title):
    return f"https://www.linkedin.com/search/results/people/?keywords={urllib.parse.quote(f'{company} {title}')}"


def handle_error(e, context=""):
    msg = str(e)
    if "rate_limit" in msg or "429" in msg:
        st.caption(f"⏳ Rate limit reached{' — ' + context + ' skipped' if context else ''}. Wait ~60s before retrying.")
    else:
        st.error(f"Error: {msg[:120]}")


def highlight_priority(val):
    m = {'High': 'background-color:#DCFCE7;color:#166534',
         'Medium': 'background-color:#FEF9C3;color:#854D0E',
         'Low': 'background-color:#FEE2E2;color:#991B1B',
         'Already Partner': 'background-color:#DBEAFE;color:#1E40AF'}
    return m.get(val, '')


def highlight_confidence(val):
    m = {'High': 'background-color:#DCFCE7;color:#166534',
         'Medium': 'background-color:#FEF9C3;color:#854D0E',
         'Low': 'background-color:#FEE2E2;color:#991B1B'}
    return m.get(val, '')


# ── Core Functions ────────────────────────────────────────────────────────────

def find_brands(provider, api_key, source_key, segments=None, exclude=None, count=10):
    source = LEAD_SOURCES[source_key]
    excl = f"\nDo NOT include these brands:\n{json.dumps(exclude[:200])}" if exclude else ""
    segs = ""
    if segments:
        names = [SEGMENTS[s] for s in segments if s in SEGMENTS]
        if names:
            segs = f"\nFocus ONLY on these segments: {', '.join(names)}."

    prompt = f"""Search for: {source['query']}

Find {count} US restaurant brands.{segs}
Return a JSON array with company, website, us_locations, segment, student_appeal.{excl}"""

    try:
        text = call_llm(provider, api_key, FIND_SYSTEM_PROMPT, prompt, use_search=True)
        results = parse_json_array(text)
        if not results and text:
            st.warning("LLM responded but no brands were parsed. Check the debug snippet above.")
        return results
    except Exception as e:
        handle_error(e, source["name"])
        return []


def research_brand(provider, api_key, brand_data):
    brand = brand_data.get("company", "Unknown")
    prompt = f"""Research "{brand}" for student discount status and marketing posture.
Website: {brand_data.get('website', 'Unknown')}.
US Locations: {brand_data.get('us_locations', 'Unknown')}.
Segment: {brand_data.get('segment', 'Unknown')}.

Does this brand offer a student discount? If so, through which verification provider (Student Beans, UNiDAYS, SheerID, ID.me, or in-house)?
Do they have a loyalty program or app? How strong is their Gen Z marketing?
Return JSON as specified."""

    try:
        text = call_llm(provider, api_key, RESEARCH_SYSTEM_PROMPT, prompt, use_search=True)
        result = parse_json_object(text)
        if result:
            result["company"] = brand
        return result
    except Exception as e:
        handle_error(e, brand)
        return {}


def find_contacts(provider, api_key, brand_data, research_data, personas, quick_mode=True):
    brand = brand_data.get("company", "Unknown")
    count_per = 1 if quick_mode else 2
    persona_lines = []
    for p in personas:
        info = PERSONAS.get(p, {})
        persona_lines.append(f"- {info['label']}: titles like {', '.join(info['titles'][:3])}")

    prompt = f"""Company: {brand}
Segment: {brand_data.get('segment', 'Unknown')}
US Locations: {brand_data.get('us_locations', 'Unknown')}
Has Student Discount: {research_data.get('has_student_discount', 'Unknown')}
Verification Provider: {research_data.get('verification_provider', 'Unknown')}

Find {len(personas) * count_per} contacts — {count_per} per persona:
{chr(10).join(persona_lines)}

Search for real people currently at this company."""

    try:
        text = call_llm(provider, api_key, CONTACTS_SYSTEM_PROMPT, prompt, use_search=True)
        contacts = parse_json_array(text)
        for c in contacts:
            c["company"] = brand
            if not c.get("linkedin_search_url"):
                c["linkedin_search_url"] = li_url(brand, c.get("title", ""))
        return contacts
    except Exception as e:
        handle_error(e, brand)
        return []


def generate_pitch(provider, api_key, brand_data, research_data, contact):
    prompt = f"""Company: {brand_data.get('company', '')}
Segment: {brand_data.get('segment', 'Unknown')}
US Locations: {brand_data.get('us_locations', 'Unknown')}
Has Student Discount: {research_data.get('has_student_discount', 'Unknown')}
Current Verification Provider: {research_data.get('verification_provider', 'None')}
Loyalty Program: {research_data.get('loyalty_program', 'Unknown')}
Gen Z Marketing: {research_data.get('gen_z_marketing', 'Unknown')}
Priority: {research_data.get('priority', 'Unknown')}

Contact: {contact.get('name', 'Unknown')} — {contact.get('title', '')} ({contact.get('persona', '')})
Why relevant: {contact.get('why_relevant', '')}

Generate a personalized pitch for this contact to adopt Pion's student discount platform."""

    try:
        text = call_llm(provider, api_key, PITCH_SYSTEM_PROMPT, prompt, use_search=False)
        result = parse_json_object(text)
        if result:
            result["company"] = brand_data.get("company", "")
            result["contact_name"] = contact.get("name", "")
            result["contact_title"] = contact.get("title", "")
            result["persona"] = contact.get("persona", "")
        return result
    except Exception as e:
        handle_error(e)
        return {}


# ── Pitch Card Renderer ──────────────────────────────────────────────────────

def render_pitch_card(p):
    if not p:
        return
    persona = p.get("persona", "")
    colors = {"Marketing Leader": "#2563EB", "Partnerships & BD": "#7C3AED", "Digital & Loyalty Owner": "#059669"}
    a = colors.get(persona, "#6B7280")

    st.markdown(f"""
    <div style="border:2px solid {a};border-radius:12px;padding:20px;margin-bottom:16px;
                background:linear-gradient(135deg,{a}08 0%,transparent 60%);">
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px;flex-wrap:wrap;">
            <span style="background:{a};color:white;padding:4px 12px;border-radius:20px;font-size:12px;
                         font-weight:700;letter-spacing:.5px;">{persona.upper()}</span>
            <span style="font-size:15px;font-weight:700;color:#111827;">{p.get('contact_name','')}</span>
            <span style="font-size:13px;color:#6B7280;">{p.get('contact_title','')} at {p.get('company','')}</span>
        </div>
        <p style="font-size:14px;font-style:italic;color:#374151;margin:0;line-height:1.5;">"{p.get('pitch_angle','')}"</p>
    </div>""", unsafe_allow_html=True)

    cl, cr = st.columns(2)
    with cl:
        st.markdown("**✉️ Cold Email**")
        st.markdown(f"""<div style="background:#EFF6FF;border:1px solid #93C5FD;padding:12px;border-radius:8px;margin-bottom:12px;">
            <p style="font-size:12px;color:#1E40AF;margin:0 0 6px 0;"><strong>Subject:</strong> {p.get('email_subject','')}</p>
            <p style="font-size:13px;color:#1F2937;margin:0;line-height:1.5;">{p.get('opening_line','')}</p></div>""", unsafe_allow_html=True)
        st.markdown("**🎯 Talking Points**")
        for i, tp in enumerate(p.get("talking_points", []), 1):
            st.markdown(f"""<div style="background:#F8FAFC;border-left:3px solid {a};padding:8px 12px;margin-bottom:6px;
                        border-radius:0 8px 8px 0;font-size:13px;color:#374151;">
                <strong style="color:{a};">{i}.</strong> {tp}</div>""", unsafe_allow_html=True)
    with cr:
        if p.get("estimated_impact"):
            st.markdown("**📈 Estimated Impact**")
            st.markdown(f"""<div style="background:#F0FDF4;border:1px solid #86EFAC;padding:10px;border-radius:8px;
                        font-size:13px;color:#166534;margin-bottom:12px;">{p['estimated_impact']}</div>""", unsafe_allow_html=True)
        if p.get("objection"):
            st.markdown("**🛡️ Objection**")
            st.markdown(f"""<div style="background:#FEF2F2;border:1px solid #FCA5A5;padding:10px;border-radius:8px;margin-bottom:12px;">
                <p style="font-size:12px;color:#991B1B;margin:0 0 6px 0;"><strong>They'll say:</strong> "{p['objection']}"</p>
                <p style="font-size:12px;color:#1F2937;margin:0;"><strong>You say:</strong> {p.get('objection_response','')}</p></div>""", unsafe_allow_html=True)
        if p.get("call_to_action"):
            st.markdown("**🎬 CTA**")
            st.markdown(f"""<div style="background:#F5F3FF;border:1px solid #C4B5FD;padding:10px;border-radius:8px;
                        font-size:13px;color:#5B21B6;">{p['call_to_action']}</div>""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════
st.sidebar.title("⚙️ Settings")
provider = st.sidebar.selectbox("Provider", ["anthropic", "gemini", "perplexity", "openai"],
    help="Anthropic and Gemini both include live web search. Gemini has generous free-tier rate limits.")
env_keys = {"perplexity": "PERPLEXITY_API_KEY", "anthropic": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY"}
env_var = env_keys.get(provider, "")
default_key = _get_secret(env_var)
api_key = st.sidebar.text_input("API Key", value=default_key, type="password")

st.sidebar.markdown("---")

# Cost info
cost_map = {"perplexity": "$0.005", "anthropic": "$0.015", "openai": "$0.025", "gemini": "$0.010"}
st.sidebar.caption(f"Est. cost per lead: {cost_map.get(provider, '?')}")
st.sidebar.caption("Built for Pion — Student Discount Lead Research")

# ── Session State ─────────────────────────────────────────────────────────────
for k in ['found_brands', 'research_results', 'contacts', 'pitches', 'brand_names_db']:
    if k not in st.session_state:
        st.session_state[k] = [] if k != 'research_results' else {}

def normalise(n):
    return n.strip().lower()


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════
st.title("🎓 Pion Restaurant Lead Enricher")
st.caption("Find → Research → Contacts → Pitch")

tab1, tab2, tab3, tab4 = st.tabs(["🔍 Find", "🔬 Research", "👥 Contacts", "✉️ Pitch"])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1: FIND
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.header("Find Brands")
    st.markdown("Search for US restaurant brands to evaluate for student discount partnerships. "
                "Returns **brand name, website, locations, segment, and student appeal**.")

    with st.expander("📂 Upload exclusion list (optional)", expanded=False):
        st.caption("Upload a CSV of brands to exclude (e.g. existing partners).")
        seed_file = st.file_uploader("Upload CSV", type=["csv"], key="seed")
        if seed_file:
            sdf = pd.read_csv(seed_file)
            col = next((c for c in sdf.columns if c.lower() in ['company', 'name', 'brand', 'organization']), sdf.columns[0])
            new = sdf[col].dropna().astype(str).tolist()
            exist = {normalise(n) for n in st.session_state['brand_names_db']}
            added = [n for n in new if normalise(n) not in exist]
            st.session_state['brand_names_db'].extend(added)
            st.success(f"✅ Added {len(added)} to exclusion list")

    st.markdown("---")

    st.subheader("Lead Sources")
    st.caption("Select where to search — General is recommended for most use cases")
    selected_sources = []
    src_cols = st.columns(4)
    for i, (k, s) in enumerate(LEAD_SOURCES.items()):
        with src_cols[i]:
            if st.checkbox(s["name"], help=s["description"]):
                selected_sources.append(k)

    st.subheader("Segment Filters")
    st.caption("Narrow by restaurant type — leave all unchecked for all segments")
    selected_segments = []
    vc = st.columns(4)
    for i, (k, label) in enumerate(SEGMENTS.items()):
        with vc[i % 4]:
            if st.checkbox(label, key=f"s_{k}"):
                selected_segments.append(k)

    db_ct = len(st.session_state['brand_names_db'])
    if db_ct:
        st.info(f"🔒 Exclusion active — {db_ct} brands excluded.")

    st.markdown("---")
    speed1 = st.radio("Speed", ["⚡ Lightning (5 brands)", "🚀 Quick (10 brands)", "📊 Full (20 brands)"],
                      horizontal=True, key="speed1",
                      help="Lightning is best for demos and rate-limited accounts.")
    count_map = {"⚡ Lightning (5 brands)": 5, "🚀 Quick (10 brands)": 10, "📊 Full (20 brands)": 20}
    find_count = count_map[speed1]
    st.caption(f"{find_count} brands per source")

    if st.button("🔍 Find Brands", type="primary", disabled=not api_key or not selected_sources):
        all_r = []
        prog = st.progress(0)
        stat = st.empty()
        for i, sk in enumerate(selected_sources):
            stat.write(f"Searching {LEAD_SOURCES[sk]['name']}...")
            r = find_brands(provider, api_key, sk, selected_segments,
                            st.session_state['brand_names_db'], find_count)
            all_r.extend(r)
            prog.progress((i + 1) / len(selected_sources))
            if i < len(selected_sources) - 1:
                time.sleep(10)
        # Dedup
        seen = set()
        deduped = []
        for r in all_r:
            n = normalise(r.get("company", ""))
            if n and n not in seen:
                seen.add(n)
                deduped.append(r)
                st.session_state['brand_names_db'].append(r.get("company", ""))
        st.session_state['found_brands'] = deduped
        stat.write(f"✅ Found {len(deduped)} brands")

    # Results
    if st.session_state['found_brands']:
        brands = st.session_state['found_brands']
        st.markdown("---")
        st.subheader(f"📋 Found Brands ({len(brands)})")
        rows = [{"Brand": c.get("company", ""), "Website": c.get("website", ""),
                 "US Locations": c.get("us_locations", ""), "Segment": c.get("segment", ""),
                 "Student Appeal": c.get("student_appeal", "")} for c in brands]
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True,
                     column_config={"Website": st.column_config.LinkColumn("Website")})
        st.download_button("📥 Export CSV", df.to_csv(index=False),
                          f"pion_find_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", "text/csv", key="t1x")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2: RESEARCH
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.header("Research")
    st.markdown("Deep-dive into each brand's **student discount status, verification provider, loyalty program, and Gen Z marketing**. "
                "Each call searches the web for the latest info.")

    brands = st.session_state.get('found_brands', [])

    st.subheader("Select Brands")
    input_method = st.radio("Input method", ["From Find tab", "Upload CSV", "Enter manually"],
                           horizontal=True, key="r_input")

    research_brands = []

    if input_method == "From Find tab":
        if not brands:
            st.info("No brands found yet. Run the **Find** tab first, or use CSV upload / manual entry.")
        else:
            opts = [c.get("company", "") for c in brands]
            sel = st.multiselect("Choose brands to research", opts, default=opts[:5], key="r_sel")
            research_brands = [next((c for c in brands if c.get("company") == n), {"company": n}) for n in sel]

    elif input_method == "Upload CSV":
        csv_file = st.file_uploader("Upload CSV with brand names", type=["csv"], key="r_csv")
        if csv_file:
            df_up = pd.read_csv(csv_file)
            col = next((c for c in df_up.columns if c.lower() in ['company', 'name', 'brand', 'organization']), df_up.columns[0])
            names = df_up[col].dropna().astype(str).tolist()
            research_brands = [{"company": n} for n in names]
            st.caption(f"{len(research_brands)} brands loaded from CSV")

    elif input_method == "Enter manually":
        manual = st.text_area("Brand names (one per line)", placeholder="Sweetgreen\nShake Shack\nCAVA", height=120, key="r_manual")
        if manual:
            names = [n.strip() for n in manual.split('\n') if n.strip()]
            research_brands = [{"company": n} for n in names]
            st.caption(f"{len(research_brands)} brands entered")

    if research_brands:
        sel_names = [c.get("company", "") for c in research_brands]

        st.markdown("---")
        st.caption(f"{len(sel_names)} brands selected — {len(sel_names)} API calls")

        if st.button("🔬 Research Brands", type="primary", disabled=not api_key or not sel_names):
            prog = st.progress(0)
            stat = st.empty()

            for i, name in enumerate(sel_names):
                stat.write(f"Researching {name} ({i + 1}/{len(sel_names)})...")
                cdata = next((c for c in research_brands if c.get("company") == name), {"company": name})
                result = research_brand(provider, api_key, cdata)
                if result:
                    st.session_state['research_results'][name] = result
                    if not any(c.get("company") == name for c in st.session_state['found_brands']):
                        st.session_state['found_brands'].append(cdata)

                prog.progress((i + 1) / len(sel_names))
                if i < len(sel_names) - 1:
                    time.sleep(10)
            stat.write(f"✅ Researched {len(sel_names)} brands")

    # Results
    research = st.session_state.get('research_results', {})
    if research:
        st.markdown("---")

        res_col, legend_col = st.columns([3, 1])

        with legend_col:
            st.markdown("#### Priority Scoring")
            st.markdown("""
            <div style="font-size:12px;line-height:1.8;">
                <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px;">
                    <span style="background:#DCFCE7;color:#166534;padding:2px 8px;border-radius:4px;font-weight:600;font-size:11px;">High</span>
                    <span>Uses competitor verification — pitch Pion</span>
                </div>
                <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px;">
                    <span style="background:#FEF9C3;color:#854D0E;padding:2px 8px;border-radius:4px;font-weight:600;font-size:11px;">Medium</span>
                    <span>US presence, no student discount yet</span>
                </div>
                <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px;">
                    <span style="background:#DBEAFE;color:#1E40AF;padding:2px 8px;border-radius:4px;font-weight:600;font-size:11px;">Already Partner</span>
                    <span>On Pion / Student Beans — skip or upsell</span>
                </div>
                <div style="display:flex;align-items:center;gap:6px;">
                    <span style="background:#FEE2E2;color:#991B1B;padding:2px 8px;border-radius:4px;font-weight:600;font-size:11px;">Low</span>
                    <span>No US presence or too small</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

        with res_col:
            st.subheader(f"📋 Research Results ({len(research)})")

            priority_filter = st.multiselect("Filter by Priority", ["High", "Medium", "Already Partner", "Low"],
                                             default=["High", "Medium"], key="t2_pf")

            priorities = [v.get("priority", "") for v in research.values()]
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("🟢 High", priorities.count("High"))
            m2.metric("🟡 Medium", priorities.count("Medium"))
            m3.metric("🔵 Already Partner", priorities.count("Already Partner"))
            m4.metric("🔴 Low", priorities.count("Low"))

            r_rows = []
            for name, r in research.items():
                r_rows.append({
                    "Brand": name,
                    "Student Discount": "✅ Yes" if r.get("has_student_discount") else "❌ No",
                    "Verification": r.get("verification_provider", "None"),
                    "Loyalty Program": (str(r.get("loyalty_program", ""))[:40] + "…") if len(str(r.get("loyalty_program", ""))) > 40 else str(r.get("loyalty_program", "")),
                    "Gen Z Marketing": (str(r.get("gen_z_marketing", ""))[:40] + "…") if len(str(r.get("gen_z_marketing", ""))) > 40 else str(r.get("gen_z_marketing", "")),
                    "Priority": r.get("priority", ""),
                    "Rationale": r.get("priority_rationale", ""),
                })
            df_r = pd.DataFrame(r_rows)
            if priority_filter:
                df_r_display = df_r[df_r["Priority"].isin(priority_filter)]
            else:
                df_r_display = df_r

            pri_ord = {"High": 0, "Medium": 1, "Already Partner": 2, "Low": 3}
            df_r_display = df_r_display.copy()
            df_r_display["_sort"] = df_r_display["Priority"].map(pri_ord)
            df_r_display = df_r_display.sort_values("_sort").drop(columns=["_sort"])

            styled = df_r_display.style.map(highlight_priority, subset=["Priority"])
            st.dataframe(styled, use_container_width=True, hide_index=True)

            st.download_button("📥 Export Research CSV", df_r.to_csv(index=False),
                              f"pion_research_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", "text/csv", key="t2x")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3: CONTACTS
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.header("Contacts")
    st.markdown("Find decision-makers at researched brands. "
                "Select **personas** to target and which brands to search.")

    research = st.session_state.get('research_results', {})
    brands = st.session_state.get('found_brands', [])

    if not research:
        st.info("No brands researched yet. Go to the **Research** tab first.")
    else:
        st.subheader("Persona Filters")
        st.caption("Select which buying personas to search for")
        sel_personas = []
        pc = st.columns(3)
        for i, (k, info) in enumerate(PERSONAS.items()):
            with pc[i]:
                if st.checkbox(info["label"], value=True, help=info["description"], key=f"p_{k}"):
                    sel_personas.append(k)
                st.caption(f"e.g. {', '.join(info['titles'][:3])}")

        if not sel_personas:
            st.warning("Select at least one persona.")

        st.subheader("Select Brands")
        researched_names = list(research.keys())
        priority_map = {n: research[n].get("priority", "") for n in researched_names}
        c_opts = [f"{n}  ({priority_map.get(n, '')})" for n in researched_names]
        sel_c = st.multiselect("Choose brands", c_opts, default=c_opts[:3], key="c_sel")
        sel_c_names = [o.rsplit("  (", 1)[0] for o in sel_c]

        st.markdown("---")
        qm3 = st.toggle("⚡ Quick Mode", value=True, key="qm3",
                         help="On: 1 contact/persona. Off: 2 contacts/persona.")
        cper = 1 if qm3 else 2
        st.caption(f"{len(sel_personas)} personas × {cper} contacts × {len(sel_c_names)} brands = "
                   f"~{len(sel_c_names)} API calls")

        if st.button("👥 Find Contacts", type="primary",
                     disabled=not api_key or not sel_c_names or not sel_personas):
            all_contacts = []
            prog = st.progress(0)
            stat = st.empty()

            contacts_by_brand: Dict[str, list] = {}

            for i, name in enumerate(sel_c_names):
                stat.write(f"Finding contacts at {name} ({i + 1}/{len(sel_c_names)})...")
                cdata = next((c for c in brands if c.get("company") == name), {"company": name})
                rdata = research.get(name, {})
                cts = find_contacts(provider, api_key, cdata, rdata, sel_personas, qm3)
                if cts:
                    all_contacts.extend(cts)
                    contacts_by_brand[name] = cts
                prog.progress((i + 1) / len(sel_c_names))
                if i < len(sel_c_names) - 1:
                    time.sleep(10)

            st.session_state['contacts'] = all_contacts
            stat.write(f"✅ Found {len(all_contacts)} contacts")

    # Results
    if st.session_state.get('contacts'):
        contacts = st.session_state['contacts']
        st.markdown("---")
        st.subheader(f"📋 Contacts ({len(contacts)})")

        fc1, fc2, fc3 = st.columns(3)
        with fc1:
            pf = st.multiselect("Filter by Persona",
                list({c.get("persona", "") for c in contacts}),
                default=list({c.get("persona", "") for c in contacts}), key="t3_pf")
        with fc2:
            cf = st.multiselect("Filter by Brand",
                sorted({c.get("company", "") for c in contacts}), key="t3_cf")
        with fc3:
            conf_f = st.multiselect("Filter by Confidence", ["High", "Medium", "Low"],
                default=["High", "Medium", "Low"], key="t3_conf")

        c_rows = [{"Brand": c.get("company", ""), "Name": c.get("name", ""), "Title": c.get("title", ""),
                   "Persona": c.get("persona", ""), "Seniority": c.get("seniority", ""),
                   "Why Relevant": c.get("why_relevant", ""),
                   "Confidence": c.get("confidence", "").split(" ")[0] if c.get("confidence") else "",
                   "LinkedIn": c.get("linkedin_search_url", "")} for c in contacts]
        df_c = pd.DataFrame(c_rows)

        filtered = df_c.copy()
        if pf:
            filtered = filtered[filtered["Persona"].isin(pf)]
        if cf:
            filtered = filtered[filtered["Brand"].isin(cf)]
        if conf_f:
            filtered = filtered[filtered["Confidence"].isin(conf_f)]

        pm1, pm2, pm3 = st.columns(3)
        pm1.metric("📣 Marketing Leaders", len(df_c[df_c["Persona"] == "Marketing Leader"]))
        pm2.metric("🤝 Partnerships / BD", len(df_c[df_c["Persona"] == "Partnerships & BD"]))
        pm3.metric("📱 Digital / Loyalty", len(df_c[df_c["Persona"] == "Digital & Loyalty Owner"]))

        styled = filtered.style.map(highlight_confidence, subset=["Confidence"])
        st.dataframe(styled, use_container_width=True, hide_index=True,
                     column_config={"LinkedIn": st.column_config.LinkColumn("LinkedIn", display_text="🔗 Search")})

        st.download_button("📥 Export Contacts CSV", df_c.to_csv(index=False),
                          f"pion_contacts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", "text/csv", key="t3x")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4: PITCH
# ══════════════════════════════════════════════════════════════════════════════
with tab4:
    st.header("Pitch")
    st.markdown("Generate personalized outreach using data from all prior tabs. Each pitch references the "
                "**contact's persona**, the **brand's discount status**, and relevant **pain points**.")

    contacts = st.session_state.get('contacts', [])
    research = st.session_state.get('research_results', {})
    brands = st.session_state.get('found_brands', [])

    if not contacts:
        st.info("No contacts found yet. Go to the **Contacts** tab first.")
    else:
        st.subheader("Select Contacts to Pitch")

        sel_mode = st.radio("Selection mode", ["By Brand (all contacts)", "Individual Contacts"],
                           horizontal=True, help="By Brand: pitch everyone at selected brands. Individual: pick specific people.")

        sel_contacts = []
        if sel_mode == "By Brand (all contacts)":
            cos = sorted({c.get("company", "") for c in contacts})
            sel_cos = st.multiselect("Select brands", cos, key="p_cos")
            sel_contacts = [c for c in contacts if c.get("company") in sel_cos]
            if sel_contacts:
                st.caption(f"{len(sel_contacts)} contacts across {len(sel_cos)} brands")
        else:
            p_pf = st.multiselect("Filter by Persona",
                ["Marketing Leader", "Partnerships & BD", "Digital & Loyalty Owner"],
                default=["Marketing Leader", "Partnerships & BD", "Digital & Loyalty Owner"], key="p_pf")
            labels = {}
            for c in contacts:
                if c.get("persona") in p_pf:
                    l = f"{c.get('name', '?')} — {c.get('title', '')} at {c.get('company', '')} ({c.get('persona', '')})"
                    labels[l] = c
            sel_labels = st.multiselect("Select contacts", list(labels.keys()), key="p_sel")
            sel_contacts = [labels[l] for l in sel_labels]

        if sel_contacts:
            st.caption(f"{len(sel_contacts)} pitch(es) — {len(sel_contacts)} API calls (no web search, faster)")
            if st.button("✉️ Generate Pitches", type="primary", disabled=not api_key):
                all_p = []
                prog = st.progress(0)
                stat = st.empty()

                for i, ct in enumerate(sel_contacts):
                    cn = ct.get("company", "")
                    stat.write(f"Pitching {ct.get('name', '?')} at {cn} ({i + 1}/{len(sel_contacts)})...")
                    cdata = next((c for c in brands if c.get("company") == cn), {"company": cn})
                    rdata = research.get(cn, {})
                    pitch = generate_pitch(provider, api_key, cdata, rdata, ct)
                    if pitch:
                        all_p.append(pitch)

                    prog.progress((i + 1) / len(sel_contacts))
                    if i < len(sel_contacts) - 1:
                        time.sleep(5)
                st.session_state['pitches'].extend(all_p)
                stat.write(f"✅ Generated {len(all_p)} pitches")

    # Results
    if st.session_state.get('pitches'):
        pitches = st.session_state['pitches']
        st.markdown("---")
        st.subheader(f"📋 Generated Pitches ({len(pitches)})")

        pf1, pf2 = st.columns(2)
        with pf1:
            p_cf = st.multiselect("Filter by Brand",
                sorted({p.get("company", "") for p in pitches}), key="t4_cf")
        with pf2:
            p_pf2 = st.multiselect("Filter by Persona",
                sorted({p.get("persona", "") for p in pitches}),
                default=sorted({p.get("persona", "") for p in pitches}), key="t4_pf")

        fp = pitches
        if p_cf:
            fp = [p for p in fp if p.get("company") in p_cf]
        if p_pf2:
            fp = [p for p in fp if p.get("persona") in p_pf2]

        for pitch in fp:
            render_pitch_card(pitch)
            st.markdown("")

        exp = [{"Brand": p.get("company", ""), "Contact": p.get("contact_name", ""),
                "Title": p.get("contact_title", ""), "Persona": p.get("persona", ""),
                "Subject": p.get("email_subject", ""), "Opening": p.get("opening_line", ""),
                "Angle": p.get("pitch_angle", ""),
                "TP1": p.get("talking_points", [""])[0] if p.get("talking_points") else "",
                "TP2": p.get("talking_points", ["", ""])[1] if len(p.get("talking_points", [])) > 1 else "",
                "TP3": p.get("talking_points", ["", "", ""])[2] if len(p.get("talking_points", [])) > 2 else "",
                "Impact": p.get("estimated_impact", ""),
                "Objection": p.get("objection", ""), "Response": p.get("objection_response", ""),
                "CTA": p.get("call_to_action", "")} for p in pitches]
        st.download_button("📥 Export Pitches CSV", pd.DataFrame(exp).to_csv(index=False),
                          f"pion_pitches_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", "text/csv", key="t4x")
