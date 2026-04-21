#!/usr/bin/env python3
"""
Pion Restaurant Lead Enricher - CLI
Multi-Provider Edition with configurable waterfall fallback.

Researches restaurant brands for student discount status using multiple AI providers.

Providers supported:
- perplexity: Sonar with native search ($0.005/lead) - CHEAPEST
- anthropic: Claude with web search ($0.015/lead)
- gemini: Gemini 2.5 Flash with Google Search ($0.010/lead)
- openai: GPT-4o ($0.025/lead)

Usage:
    python enricher.py                           # Interactive mode, uses config
    python enricher.py brands.csv                # Process CSV
    python enricher.py "Sweetgreen, Chipotle"    # Direct list
    python enricher.py --provider anthropic       # Use specific provider
    python enricher.py --config                  # Edit API keys and settings

Environment variables (or use --config to set):
    ANTHROPIC_API_KEY
    OPENAI_API_KEY
    PERPLEXITY_API_KEY
    GEMINI_API_KEY
"""

import os
import sys
import csv
import json
import re
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

try:
    from rich.console import Console
    from rich.table import Table
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm
except ImportError:
    print("Installing required packages...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "rich", "-q"])
    from rich.console import Console
    from rich.table import Table
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm

console = Console()

CONFIG_FILE = Path.home() / ".pion_enricher_config.json"

DEFAULT_CONFIG = {
    "providers": {
        "perplexity": {
            "api_key": "",
            "model": "sonar",
            "cost_per_lead": 0.005,
            "enabled": True
        },
        "anthropic": {
            "api_key": "",
            "model": "claude-sonnet-4-5",
            "cost_per_lead": 0.015,
            "enabled": True
        },
        "gemini": {
            "api_key": "",
            "model": "gemini-2.5-flash",
            "cost_per_lead": 0.010,
            "enabled": True
        },
        "openai": {
            "api_key": "",
            "model": "gpt-4o",
            "cost_per_lead": 0.025,
            "enabled": True
        },
    },
    "waterfall_order": ["perplexity", "anthropic", "gemini", "openai"],
    "default_provider": "perplexity"
}

SYSTEM_PROMPT = """You are a research assistant for Pion, a student discount and loyalty platform. Your job is to research restaurant brands and determine their student discount status, verification providers, and sales priority for Pion's partnership team.

For each brand, search the web and return ONLY this JSON object with no other text:
{
    "company": "Brand Name",
    "website": "official website URL",
    "us_presence": true/false,
    "us_locations": "number or estimate",
    "has_student_discount": true/false,
    "discount_details": "describe the student discount or None",
    "discount_url": "URL to student discount page or empty string",
    "verification_provider": "Student Beans / UNiDAYS / SheerID / ID.me / In-house / None",
    "loyalty_program": "describe loyalty/rewards program or None",
    "app_available": true/false,
    "social_media_presence": "strong / moderate / weak",
    "gen_z_marketing": "describe any Gen Z / college targeting or None",
    "competitor_discounts": "which similar brands offer student discounts",
    "priority": "High / Medium / Low / Already Partner",
    "priority_rationale": "one sentence",
    "recommended_contacts": "titles to target e.g. VP Marketing, Head of Partnerships, Director of Loyalty",
    "linkedin_search_url": "https://www.linkedin.com/search/results/people/?keywords=BRAND%20VP%20Marketing%20Partnerships",
    "notes": "anything else useful for the sales team"
}

Priority logic:
- High: Uses a competitor verification provider (Student Beans, UNiDAYS, SheerID) — pitch Pion as better value and reach
- Medium: US presence, no student discount yet — greenfield opportunity to launch one
- Already Partner: Already uses Pion or has Pion-powered discount — skip or upsell
- Low: No US presence or very small brand

Return ONLY the JSON object. No markdown, no explanation, no code fences."""


def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                for provider, settings in DEFAULT_CONFIG["providers"].items():
                    if provider not in config.get("providers", {}):
                        config.setdefault("providers", {})[provider] = settings
                return config
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()


def save_config(config: dict):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)
    console.print(f"[green]Config saved to {CONFIG_FILE}[/green]")


def configure_interactive():
    config = load_config()

    console.print(Panel.fit(
        "[bold cyan]Pion Lead Enricher Configuration[/bold cyan]\n\n"
        "Configure your API keys and provider preferences.",
        title="Settings"
    ))

    console.print("\n[bold]Current Provider Status:[/bold]")
    table = Table(show_header=True)
    table.add_column("Provider")
    table.add_column("API Key")
    table.add_column("Cost/Lead")
    table.add_column("Enabled")

    for name, settings in config["providers"].items():
        key_status = "✓ Set" if settings.get("api_key") else "✗ Not set"
        key_style = "green" if settings.get("api_key") else "red"
        table.add_row(
            name,
            f"[{key_style}]{key_status}[/{key_style}]",
            f"${settings.get('cost_per_lead', 0):.3f}",
            "Yes" if settings.get("enabled") else "No"
        )
    console.print(table)

    console.print("\n[bold]Configure Providers:[/bold]")
    for name in ["perplexity", "anthropic", "gemini", "openai"]:
        settings = config["providers"].get(name, {})
        if Confirm.ask(f"\nConfigure {name}?", default=False):
            current_key = settings.get("api_key", "")
            masked = f"...{current_key[-8:]}" if current_key else "not set"
            new_key = Prompt.ask(f"  API Key (current: {masked})", default="", password=True)
            if new_key:
                config["providers"][name]["api_key"] = new_key
            config["providers"][name]["enabled"] = Confirm.ask(
                f"  Enable {name}?", default=settings.get("enabled", True))

    console.print("\n[bold]Waterfall Order:[/bold]")
    console.print(f"  Current: {' → '.join(config.get('waterfall_order', []))}")
    if Confirm.ask("Change waterfall order?", default=False):
        console.print("  Available: perplexity, anthropic, gemini, openai")
        order_input = Prompt.ask("  Order", default="perplexity,anthropic,gemini,openai")
        config["waterfall_order"] = [p.strip() for p in order_input.split(",")]

    config["default_provider"] = Prompt.ask(
        "\nDefault provider",
        choices=["perplexity", "anthropic", "gemini", "openai"],
        default=config.get("default_provider", "perplexity")
    )

    save_config(config)
    console.print("\n[bold green]Configuration complete![/bold green]")


def get_api_key(provider: str, config: dict) -> Optional[str]:
    key = config.get("providers", {}).get(provider, {}).get("api_key")
    if key:
        return key
    env_map = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "perplexity": "PERPLEXITY_API_KEY",
        "gemini": "GEMINI_API_KEY"
    }
    return os.environ.get(env_map.get(provider, ""))


def _clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'```(?:json|JSON)?\s*', '', text)
    text = text.replace('```', '')
    return text.strip()


def parse_json_response(text: str, company_name: str) -> dict:
    text = _clean_text(text)
    try:
        start = text.find('{')
        end = text.rfind('}') + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
    except json.JSONDecodeError:
        pass
    return {
        "company": company_name,
        "website": "",
        "us_presence": False,
        "has_student_discount": False,
        "verification_provider": "Error",
        "priority": "Error",
        "notes": f"Parse error: {text[:100]}"
    }


def enrich_with_anthropic(company_name: str, api_key: str, model: str) -> dict:
    try:
        from anthropic import Anthropic
    except ImportError:
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "anthropic", "-q"])
        from anthropic import Anthropic

    client = Anthropic(api_key=api_key)
    message = client.messages.create(
        model=model, max_tokens=2048,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        system=SYSTEM_PROMPT,
        messages=[{"role": "user",
                   "content": f'Research "{company_name}" for Pion student discount sales prospecting. Find their student discount status, verification provider, loyalty program, and Gen Z marketing efforts. Return only JSON.'}]
    )
    text_content = "".join(b.text for b in message.content if hasattr(b, 'text'))
    return parse_json_response(text_content, company_name)


def enrich_with_gemini(company_name: str, api_key: str, model: str) -> dict:
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "google-genai", "-q"])
        from google import genai
        from google.genai import types

    client = genai.Client(api_key=api_key)
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=[types.Tool(google_search=types.GoogleSearch())],
    )
    response = client.models.generate_content(
        model=model,
        contents=f'Research "{company_name}" for Pion student discount sales prospecting. Find their student discount status, verification provider, loyalty program, and Gen Z marketing efforts. Return only JSON.',
        config=config,
    )
    if response.text:
        return parse_json_response(response.text, company_name)
    try:
        parts = response.candidates[0].content.parts
        text = "".join(p.text for p in parts if hasattr(p, "text") and p.text) or ""
        return parse_json_response(text, company_name)
    except Exception:
        return parse_json_response("", company_name)


def enrich_with_openai(company_name: str, api_key: str, model: str) -> dict:
    try:
        from openai import OpenAI
    except ImportError:
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "openai", "-q"])
        from openai import OpenAI

    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f'Research "{company_name}" for Pion student discount sales prospecting. Find their student discount status, verification provider, loyalty program, and Gen Z marketing efforts. Return only JSON.'}
        ]
    )
    return parse_json_response(response.choices[0].message.content, company_name)


def enrich_with_perplexity(company_name: str, api_key: str, model: str) -> dict:
    try:
        from openai import OpenAI
    except ImportError:
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "openai", "-q"])
        from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url="https://api.perplexity.ai")
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f'Research "{company_name}" for Pion student discount sales prospecting. Search for their student discount page, verification provider (Student Beans, UNiDAYS, SheerID, ID.me), loyalty program, and Gen Z marketing. Return only JSON.'}
        ]
    )
    return parse_json_response(response.choices[0].message.content, company_name)


def enrich_company(company_name: str, config: dict, provider: Optional[str] = None) -> tuple:
    if provider:
        providers_to_try = [provider]
    else:
        providers_to_try = config.get("waterfall_order", ["perplexity", "anthropic", "gemini", "openai"])

    for prov in providers_to_try:
        settings = config.get("providers", {}).get(prov, {})
        if not settings.get("enabled", True):
            continue
        api_key = get_api_key(prov, config)
        if not api_key:
            continue
        model = settings.get("model", "")

        try:
            if prov == "anthropic":
                result = enrich_with_anthropic(company_name, api_key, model)
            elif prov == "gemini":
                result = enrich_with_gemini(company_name, api_key, model)
            elif prov == "openai":
                result = enrich_with_openai(company_name, api_key, model)
            elif prov == "perplexity":
                result = enrich_with_perplexity(company_name, api_key, model)
            else:
                continue

            if result.get("priority") != "Error":
                return result, prov
        except Exception as e:
            console.print(f"[yellow]  {prov} failed: {str(e)[:50]}[/yellow]")
            continue

    return {
        "company": company_name, "website": "", "us_presence": False,
        "has_student_discount": False, "verification_provider": "Error",
        "priority": "Error", "notes": "All providers failed"
    }, "none"


def generate_linkedin_url(company_name: str) -> str:
    import urllib.parse
    query = f"{company_name} VP Marketing Head of Partnerships Director Loyalty"
    return f"https://www.linkedin.com/search/results/people/?keywords={urllib.parse.quote(query)}"


def display_results(results: list, providers_used: dict):
    table = Table(title="Pion Restaurant Lead Research Results", show_lines=True)
    table.add_column("Brand", style="cyan", no_wrap=True)
    table.add_column("US Locs", width=8)
    table.add_column("Student Disc.", width=12)
    table.add_column("Verification", width=14)
    table.add_column("Loyalty", width=14)
    table.add_column("Priority", width=16)
    table.add_column("Source", width=10, style="dim")

    priority_colors = {"High": "green", "Medium": "yellow", "Low": "red",
                       "Already Partner": "blue", "Error": "red"}

    for r in results:
        priority = r.get("priority", "Unknown")
        p_style = priority_colors.get(priority, "white")
        company = r.get("company", "")
        has_disc = "✅ Yes" if r.get("has_student_discount") else "❌ No"
        loyalty = str(r.get("loyalty_program", ""))[:14]
        if len(str(r.get("loyalty_program", ""))) > 14:
            loyalty += "…"

        table.add_row(
            company,
            str(r.get("us_locations", ""))[:8],
            has_disc,
            r.get("verification_provider", "None")[:14],
            loyalty,
            f"[{p_style}]{priority}[/{p_style}]",
            providers_used.get(company, "")[:10]
        )

    console.print(table)

    high = sum(1 for r in results if r.get("priority") == "High")
    med = sum(1 for r in results if r.get("priority") == "Medium")
    already = sum(1 for r in results if r.get("priority") == "Already Partner")
    low = sum(1 for r in results if r.get("priority") == "Low")

    console.print(f"\n[bold]Summary:[/bold]")
    console.print(f"  [green]High (competitor verification — pitch Pion):[/green] {high}")
    console.print(f"  [yellow]Medium (no discount — greenfield):[/yellow] {med}")
    console.print(f"  [blue]Already Partner:[/blue] {already}")
    console.print(f"  [red]Low:[/red] {low}")

    config = load_config()
    provider_counts = {}
    for p in providers_used.values():
        provider_counts[p] = provider_counts.get(p, 0) + 1
    total_cost = sum(
        config.get("providers", {}).get(prov, {}).get("cost_per_lead", 0.01) * count
        for prov, count in provider_counts.items()
    )
    console.print(f"\n[dim]Estimated API cost: ${total_cost:.2f}[/dim]")


def save_results(results: list, output_path: str):
    fieldnames = [
        "Brand", "Website", "US Presence", "US Locations",
        "Has Student Discount", "Discount Details", "Discount URL",
        "Verification Provider", "Loyalty Program", "App Available",
        "Gen Z Marketing", "Priority", "Priority Rationale",
        "Recommended Contacts", "LinkedIn Search", "Notes"
    ]

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            writer.writerow({
                "Brand": r.get("company", ""),
                "Website": r.get("website", ""),
                "US Presence": r.get("us_presence", ""),
                "US Locations": r.get("us_locations", ""),
                "Has Student Discount": r.get("has_student_discount", ""),
                "Discount Details": r.get("discount_details", ""),
                "Discount URL": r.get("discount_url", ""),
                "Verification Provider": r.get("verification_provider", ""),
                "Loyalty Program": r.get("loyalty_program", ""),
                "App Available": r.get("app_available", ""),
                "Gen Z Marketing": r.get("gen_z_marketing", ""),
                "Priority": r.get("priority", ""),
                "Priority Rationale": r.get("priority_rationale", ""),
                "Recommended Contacts": r.get("recommended_contacts", ""),
                "LinkedIn Search": generate_linkedin_url(r.get("company", "")),
                "Notes": r.get("notes", ""),
            })

    console.print(f"\n[green]✓ Results saved to:[/green] {output_path}")


def load_companies_from_csv(filepath: str) -> list:
    companies = []
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        for row in reader:
            if row and row[0].strip():
                if row[0].lower() in ['company', 'name', 'brand', 'organization', 'org']:
                    continue
                companies.append(row[0].strip())
    return companies


def process_companies(companies: list, config: dict, provider: Optional[str] = None):
    results = []
    providers_used = {}

    if provider:
        console.print(f"[cyan]Using provider: {provider}[/cyan]")
    else:
        console.print(f"[cyan]Waterfall: {' → '.join(config.get('waterfall_order', []))}[/cyan]")

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        task = progress.add_task("Researching brands...", total=len(companies))
        for company in companies:
            progress.update(task, description=f"Researching: {company}")
            result, prov_used = enrich_company(company, config, provider)
            results.append(result)
            providers_used[company] = prov_used
            progress.advance(task)

    console.print()
    display_results(results, providers_used)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = f"pion_leads_{timestamp}.csv"
    save_results(results, output_path)

    high = [r for r in results if r.get("priority") == "High"]
    if high:
        console.print(f"\n[bold green]🎯 Top targets (High priority):[/bold green]")
        for r in high:
            console.print(f"  • {r['company']}: {r.get('verification_provider', '')} — {r.get('priority_rationale', '')[:80]}")


def interactive_mode(config: dict, provider: Optional[str] = None):
    console.print(Panel.fit(
        "[bold cyan]Pion Restaurant Lead Enricher[/bold cyan]\n\n"
        "Enter brand names to research for student discount partnerships.\n"
        "Type 'done' when finished, 'quit' to exit.",
        title="Welcome"
    ))

    available = []
    for name, settings in config.get("providers", {}).items():
        if settings.get("enabled") and get_api_key(name, config):
            available.append(f"{name} (${settings.get('cost_per_lead', 0):.3f}/lead)")

    if not available:
        console.print("[red]No providers configured! Run with --config to set up.[/red]")
        return

    console.print(f"[dim]Available providers: {', '.join(available)}[/dim]")

    companies = []
    console.print("\n[bold]Enter brand names (one per line, 'done' to process):[/bold]")

    while True:
        try:
            company = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if company.lower() == 'quit':
            return
        if company.lower() == 'done':
            break
        if company:
            companies.append(company)

    if companies:
        process_companies(companies, config, provider)


def main():
    parser = argparse.ArgumentParser(
        description="Pion Restaurant Lead Enricher - Multi-Provider Edition",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python enricher.py                              # Interactive mode
    python enricher.py brands.csv                   # Process CSV
    python enricher.py "Sweetgreen, Chipotle"       # Direct list
    python enricher.py --provider anthropic          # Use specific provider
    python enricher.py --config                     # Configure API keys

Providers (by cost):
    perplexity   $0.005/lead   Cheapest, search-native
    gemini       $0.010/lead   Gemini 2.5 Flash + Google Search
    anthropic    $0.015/lead   Claude with web search
    openai       $0.025/lead   GPT-4o
        """
    )
    parser.add_argument('input', nargs='*', help='CSV file or brand names')
    parser.add_argument('--provider', '-p', choices=['anthropic', 'openai', 'perplexity', 'gemini'],
                        help='Use specific provider instead of waterfall')
    parser.add_argument('--config', '-c', action='store_true', help='Configure API keys and settings')
    parser.add_argument('--show-config', action='store_true', help='Show current configuration')

    args = parser.parse_args()

    if args.config:
        configure_interactive()
        return

    config = load_config()

    if args.show_config:
        console.print(json.dumps(config, indent=2, default=str))
        return

    has_provider = any(
        get_api_key(name, config) and config.get("providers", {}).get(name, {}).get("enabled")
        for name in config.get("waterfall_order", [])
    )

    if not has_provider:
        console.print("[yellow]No API keys configured.[/yellow]")
        console.print("Run [bold]python enricher.py --config[/bold] to set up providers.")
        console.print("\nOr set environment variables:")
        console.print("  export PERPLEXITY_API_KEY=your_key  # Cheapest")
        console.print("  export ANTHROPIC_API_KEY=your_key")
        console.print("  export GEMINI_API_KEY=your_key")
        console.print("  export OPENAI_API_KEY=your_key")
        return

    if not args.input:
        interactive_mode(config, args.provider)
    elif len(args.input) == 1 and args.input[0].endswith('.csv'):
        filepath = args.input[0]
        if not Path(filepath).exists():
            console.print(f"[red]File not found: {filepath}[/red]")
            sys.exit(1)
        companies = load_companies_from_csv(filepath)
        console.print(f"[cyan]Loaded {len(companies)} brands from {filepath}[/cyan]")
        process_companies(companies, config, args.provider)
    elif len(args.input) == 1 and ',' in args.input[0]:
        companies = [c.strip() for c in args.input[0].split(',') if c.strip()]
        process_companies(companies, config, args.provider)
    else:
        companies = [c.strip() for c in args.input if c.strip()]
        process_companies(companies, config, args.provider)


if __name__ == "__main__":
    main()
