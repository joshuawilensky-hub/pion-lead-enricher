# Pion Restaurant Lead Enricher

Four-step workflow to find, research, contact, and pitch restaurant brands for student discount partnerships.

**Find → Research → Contacts → Pitch**

## What's New

- **4-tab Streamlit UI** — full workflow from discovery to personalized outreach
- **Gemini provider** — Gemini 2.5 Flash with Google Search grounding ($0.010/lead)
- **Find tab** — discover restaurant brands by source and segment
- **Contacts tab** — find Marketing, Partnerships, and Digital/Loyalty decision-makers
- **Pitch tab** — generate persona-targeted cold emails with objection handling
- **Filters & metrics** — priority scoring, confidence levels, styled data tables
- **Multi-input** — CSV upload, manual entry, or carry forward from previous tabs

## Providers & Cost Comparison

| Provider | Cost/Lead | Notes |
|----------|-----------|-------|
| **Perplexity** | $0.005 | Cheapest, search-native |
| **Gemini** | $0.010 | Google Search grounding, generous free tier |
| **Anthropic** | $0.015 | Claude with web search |
| **OpenAI** | $0.025 | GPT-4o |

## Quick Start

### Streamlit App (Recommended)

```bash
pip install -r requirements.txt
streamlit run app.py
```

Select your provider and paste your API key in the sidebar.

### CLI Enricher

```bash
# Interactive setup
python enricher.py --config

# Or set environment variables
export PERPLEXITY_API_KEY=your_key
export ANTHROPIC_API_KEY=your_key
export GEMINI_API_KEY=your_key
export OPENAI_API_KEY=your_key

# Run
python enricher.py brands.csv
python enricher.py "Sweetgreen, Chipotle, CAVA"
python enricher.py --provider anthropic brands.csv
```

## Workflow

### 1. Find
Search for US restaurant brands by source type and segment. Sources include general search, fastest-growing chains, student-friendly brands, and brands with loyalty programs.

### 2. Research
Deep-dive into each brand's student discount status, verification provider (Student Beans, UNiDAYS, SheerID, ID.me), loyalty program, and Gen Z marketing posture.

### 3. Contacts
Find decision-makers by persona — Marketing Leaders, Partnerships/BD, and Digital/Loyalty owners. Each contact includes title, LinkedIn search URL, and confidence level.

### 4. Pitch
Generate personalized outreach with email subjects, opening lines, talking points, estimated impact, objection handling, and CTAs — all tailored to the contact's persona and the brand's current discount status.

## Priority Logic

| Priority | Meaning | Action |
|----------|---------|--------|
| **High** | Uses competitor verification (Student Beans, UNiDAYS, SheerID) | Pitch Pion as better value |
| **Medium** | US presence, no student discount | Greenfield opportunity |
| **Already Partner** | On Pion or Student Beans | Skip or upsell |
| **Low** | No US presence or tiny brand | Don't pursue |

## Output

Each tab exports CSV with all enriched data. The Research tab includes:

- Brand, Website, US Presence, US Locations
- Has Student Discount, Discount URL
- Verification Provider
- Loyalty Program, App Available
- Gen Z Marketing signals
- Priority with rationale

## API Keys

| Provider | Where to get |
|----------|-------------|
| Perplexity | https://www.perplexity.ai/settings/api |
| Gemini | https://aistudio.google.com/apikey |
| Anthropic | https://console.anthropic.com/ |
| OpenAI | https://platform.openai.com/api-keys |

## Sample Brands

```
Sweetgreen
Shake Shack
Chipotle
Panera Bread
Five Guys
Wingstop
CAVA
Portillo's
Raising Cane's
Jersey Mike's
```

## Cost Examples

| Brands | Perplexity | Gemini | Anthropic | OpenAI |
|--------|------------|--------|-----------|--------|
| 10 | $0.05 | $0.10 | $0.15 | $0.25 |
| 50 | $0.25 | $0.50 | $0.75 | $1.25 |
| 100 | $0.50 | $1.00 | $1.50 | $2.50 |

## Tips

- Start with **Perplexity** for bulk research (cheapest)
- Use **Gemini** for a good balance of cost and quality with Google Search grounding
- Use **Anthropic** for high-value targets (best quality)
- The **Find** tab is great for discovering new brands; **Research** tab works best with known brand lists
- Waterfall mode (CLI) handles rate limits and failures automatically
