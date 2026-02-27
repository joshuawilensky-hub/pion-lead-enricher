# Pion Restaurant Lead Enricher - Multi-Provider Edition

Research restaurant brands for student discount status using multiple AI providers with configurable waterfall fallback.

## Providers & Cost Comparison

| Provider | Cost/Lead | Notes |
|----------|-----------|-------|
| **Perplexity** | $0.005 | Cheapest, search-native |
| **Anthropic** | $0.015 | Claude with web search |
| **OpenAI** | $0.025 | GPT-4o with web search |

vs. alternatives:
- Apollo.io: $0.10-0.50/lead (contact data, not discount research)
- ZoomInfo: $0.50-1.00+/lead (overkill)
- Manual: $2-5/lead (your time at 10-15 min each)

## Quick Start

```bash
# Install
pip install rich anthropic openai

# Configure (interactive setup)
python enricher.py --config

# Or set environment variables
export PERPLEXITY_API_KEY=your_key
export ANTHROPIC_API_KEY=your_key
export OPENAI_API_KEY=your_key

# Run
python enricher.py
```

## Usage

### Interactive Configuration
```bash
python enricher.py --config
```
Set API keys, enable/disable providers, configure waterfall order.

### Process Brands
```bash
# Interactive mode
python enricher.py

# From CSV
python enricher.py brands.csv

# Direct list
python enricher.py "Sweetgreen, Chipotle, CAVA"
```

### Choose Provider
```bash
# Use cheapest (Perplexity)
python enricher.py --provider perplexity brands.csv

# Use Claude (best quality)
python enricher.py --provider anthropic brands.csv

# Use GPT-4o
python enricher.py --provider openai brands.csv
```

### Waterfall Mode (Default)
If no --provider specified, tries providers in order until one succeeds:
1. Perplexity (cheapest)
2. Anthropic (if Perplexity fails)
3. OpenAI (last resort)

Change order with `--config`.

## Configuration

Config saved to `~/.pion_enricher_config.json`

```json
{
  "providers": {
    "perplexity": {
      "api_key": "pplx-xxx",
      "model": "sonar",
      "cost_per_lead": 0.005,
      "enabled": true
    },
    "anthropic": {
      "api_key": "sk-ant-xxx", 
      "model": "claude-sonnet-4-20250514",
      "cost_per_lead": 0.015,
      "enabled": true
    },
    "openai": {
      "api_key": "sk-xxx",
      "model": "gpt-4o",
      "cost_per_lead": 0.025,
      "enabled": true
    }
  },
  "waterfall_order": ["perplexity", "anthropic", "openai"],
  "default_provider": "perplexity"
}
```

## Output

CSV with:
- Brand, Website, US Presence
- Has Student Discount, Discount URL
- Verification Provider (Student Beans, UNiDAYS, SheerID, ID.me, None)
- LinkedIn Search URL (pre-built)
- Priority (High/Medium/Low/Already Partner)
- Notes

## Priority Logic

| Priority | Meaning | Action |
|----------|---------|--------|
| **High** | Uses competitor verification | Pitch Pion as better value |
| **Medium** | US presence, no discount | Greenfield opportunity |
| **Already Partner** | On Student Beans/Pion | Skip or upsell |
| **Low** | No US presence | Don't pursue |

## API Keys

### Perplexity (Cheapest)
1. Go to https://www.perplexity.ai/settings/api
2. Create API key
3. Add credits ($5 minimum)

### Anthropic
1. Go to https://console.anthropic.com/
2. Create API key
3. Add credits

### OpenAI
1. Go to https://platform.openai.com/api-keys
2. Create API key
3. Add credits

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

| Brands | Perplexity | Anthropic | OpenAI |
|--------|------------|-----------|--------|
| 10 | $0.05 | $0.15 | $0.25 |
| 50 | $0.25 | $0.75 | $1.25 |
| 100 | $0.50 | $1.50 | $2.50 |

## Tips

- Start with Perplexity for bulk research (cheapest)
- Use Anthropic for high-value targets (best quality)
- Waterfall handles rate limits and failures automatically
- Results show which provider was used for each brand
