#!/usr/bin/env python3
"""
Pion Restaurant Lead Enricher - Multi-Provider Edition
Supports multiple AI providers with configurable waterfall fallback.

Providers supported:
- anthropic: Claude with web search ($0.01-0.02/lead)
- openai: GPT-4o with web search ($0.02-0.03/lead)  
- perplexity: Sonar with native search ($0.005-0.01/lead) - CHEAPEST
- gemini: Gemini 1.5 Pro ($0.010/lead)

Usage:
    python enricher.py                           # Interactive mode, uses config
    python enricher.py brands.csv                # Process CSV
    python enricher.py --provider perplexity     # Use specific provider
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
        "anthropic": {
            "api_key": "",
            "model": "claude-sonnet-4-20250514",
            "cost_per_lead": 0.015,
            "enabled": True
        },
        "perplexity": {
            "api_key": "",
            "model": "sonar",
            "cost_per_lead": 0.005,
            "enabled": True
        },
        "openai": {
            "api_key": "",
            "model": "gpt-4o",
            "cost_per_lead": 0.025,
            "enabled": True
        },
        "gemini": {
            "api_key": "",
            "model": "gemini-1.5-pro",
            "cost_per_lead": 0.010,
            "enabled": True
        }
    },
    "waterfall_order": ["perplexity", "anthropic", "openai", "gemini"],
    "default_provider": "perplexity"
}

SYSTEM_PROMPT = """You are a research assistant helping with B2B sales lead enrichment for Pion (formerly Student Beans), a student verification and discount platform.

For each restaurant brand, research and return a JSON object with these fields:
{
    "brand": "Brand Name",
    "website": "official website URL",
    "us_presence": "Yes" or "No" or "Limited" or "Unclear",
    "has_student_discount": "Yes" or "No" or "Unclear",
    "discount_url": "URL where student discount is offered (if found)",
    "verification_provider": "Student Beans" or "Pion" or "UNiDAYS" or "SheerID" or "ID.me" or "None" or "In-store ID only",
    "priority": "High" or "Medium" or "Low" or "Already Partner",
    "notes": "Brief notes on findings, competitive angle, or why to pursue/skip"
}

Priority logic:
- "High": Has student discount through competitor (UNiDAYS, SheerID, ID.me) = conversion opportunity
- "Medium": US presence, no formal student discount program = greenfield opportunity  
- "Already Partner": Already on Student Beans or Pion
- "Low": No US presence, or known to never do promos

Return ONLY the JSON object, no markdown or explanation."""


def load_config() -> dict:
    """Load config from file or create default."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                # Merge with defaults for any missing keys
                for provider, settings in DEFAULT_CONFIG["providers"].items():
                    if provider not in config.get("providers", {}):
                        config.setdefault("providers", {})[provider] = settings
                return config
        except:
            pass
    return DEFAULT_CONFIG.copy()


def save_config(config: dict):
    """Save config to file."""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)
    console.print(f"[green]Config saved to {CONFIG_FILE}[/green]")


def configure_interactive():
    """Interactive configuration of API keys and settings."""
    config = load_config()
    
    console.print(Panel.fit(
        "[bold cyan]Pion Lead Enricher Configuration[/bold cyan]\n\n"
        "Configure your API keys and provider preferences.",
        title="Settings"
    ))
    
    # Show current status
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
    
    # Configure each provider
    console.print("\n[bold]Configure Providers:[/bold]")
    for name in ["perplexity", "anthropic", "openai", "gemini"]:
        settings = config["providers"].get(name, {})
        
        if Confirm.ask(f"\nConfigure {name}?", default=False):
            # API Key
            current_key = settings.get("api_key", "")
            masked = f"...{current_key[-8:]}" if current_key else "not set"
            new_key = Prompt.ask(
                f"  API Key (current: {masked})",
                default="",
                password=True
            )
            if new_key:
                config["providers"][name]["api_key"] = new_key
            
            # Enable/disable
            config["providers"][name]["enabled"] = Confirm.ask(
                f"  Enable {name}?",
                default=settings.get("enabled", True)
            )
    
    # Waterfall order
    console.print("\n[bold]Waterfall Order:[/bold]")
    console.print("  Providers are tried in this order if one fails.")
    console.print(f"  Current: {' → '.join(config.get('waterfall_order', []))}")
    
    if Confirm.ask("Change waterfall order?", default=False):
        console.print("  Enter provider names in order (comma-separated):")
        console.print("  Available: perplexity, anthropic, openai, gemini")
        order_input = Prompt.ask("  Order", default="perplexity,anthropic,openai,gemini")
        config["waterfall_order"] = [p.strip() for p in order_input.split(",")]
    
    # Default provider
    config["default_provider"] = Prompt.ask(
        "\nDefault provider",
        choices=["perplexity", "anthropic", "openai", "gemini"],
        default=config.get("default_provider", "perplexity")
    )
    
    save_config(config)
    
    # Show final config
    console.print("\n[bold green]Configuration complete![/bold green]")
    console.print(f"Default provider: {config['default_provider']}")
    console.print(f"Waterfall order: {' → '.join(config['waterfall_order'])}")


def get_api_key(provider: str, config: dict) -> Optional[str]:
    """Get API key from config or environment."""
    # Check config first
    key = config.get("providers", {}).get(provider, {}).get("api_key")
    if key:
        return key
    
    # Fall back to environment
    env_map = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "perplexity": "PERPLEXITY_API_KEY",
        "gemini": "GEMINI_API_KEY"
    }
    return os.environ.get(env_map.get(provider, ""))


def enrich_with_anthropic(brand_name: str, api_key: str, model: str) -> dict:
    """Research brand using Claude with web search."""
    try:
        from anthropic import Anthropic
    except ImportError:
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "anthropic", "-q"])
        from anthropic import Anthropic
    
    client = Anthropic(api_key=api_key)
    
    message = client.messages.create(
        model=model,
        max_tokens=1024,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": f'Research "{brand_name}" restaurant for student discount status. Return only JSON.'
        }]
    )
    
    text_content = ""
    for block in message.content:
        if hasattr(block, 'text'):
            text_content += block.text
    
    return parse_json_response(text_content, brand_name)


def enrich_with_openai(brand_name: str, api_key: str, model: str) -> dict:
    """Research brand using OpenAI with web search."""
    try:
        from openai import OpenAI
    except ImportError:
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "openai", "-q"])
        from openai import OpenAI
    
    client = OpenAI(api_key=api_key)
    
    response = client.chat.completions.create(
        model=model,
        web_search_options={"search_context_size": "medium"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f'Research "{brand_name}" restaurant for student discount status. Return only JSON.'}
        ]
    )
    
    text_content = response.choices[0].message.content
    return parse_json_response(text_content, brand_name)


def enrich_with_perplexity(brand_name: str, api_key: str, model: str) -> dict:
    """Research brand using Perplexity Sonar (search-native, cheapest)."""
    try:
        from openai import OpenAI
    except ImportError:
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "openai", "-q"])
        from openai import OpenAI
    
    client = OpenAI(
        api_key=api_key,
        base_url="https://api.perplexity.ai"
    )
    
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f'Research "{brand_name}" restaurant for student discount status. Search for their website, US presence, and whether they offer student discounts through Student Beans, UNiDAYS, SheerID, or ID.me. Return only JSON.'}
        ]
    )
    
    text_content = response.choices[0].message.content
    return parse_json_response(text_content, brand_name)


def enrich_with_gemini(brand_name: str, api_key: str, model: str) -> dict:
    """Research brand using Google Gemini."""
    try:
        import google.generativeai as genai
    except ImportError:
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "google-generativeai", "-q"])
        import google.generativeai as genai
    
    genai.configure(api_key=api_key)
    
    # Tools parameter completely removed for stability
    llm = genai.GenerativeModel(
        model_name=model,
        system_instruction=SYSTEM_PROMPT
    )
    
    response = llm.generate_content(f'Research "{brand_name}" restaurant for student discount status. Return only JSON.')
    
    return parse_json_response(response.text, brand_name)


def parse_json_response(text: str, brand_name: str) -> dict:
    """Parse JSON from LLM response."""
    try:
        start = text.find('{')
        end = text.rfind('}') + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
    except json.JSONDecodeError:
        pass
    
    return {
        "brand": brand_name,
        "website": "",
        "us_presence": "Error",
        "has_student_discount": "Error",
        "discount_url": "",
        "verification_provider": "Error",
        "priority": "Error",
        "notes": f"Parse error: {text[:100]}"
    }


def enrich_brand(brand_name: str, config: dict, provider: Optional[str] = None) -> tuple[dict, str]:
    """
    Research a brand using configured provider(s).
    Returns (result_dict, provider_used)
    """
    # Determine provider order
    if provider:
        providers_to_try = [provider]
    else:
        providers_to_try = config.get("waterfall_order", ["perplexity", "anthropic", "openai", "gemini"])
    
    # Try each provider
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
                result = enrich_with_anthropic(brand_name, api_key, model)
            elif prov == "openai":
                result = enrich_with_openai(brand_name, api_key, model)
            elif prov == "perplexity":
                result = enrich_with_perplexity(brand_name, api_key, model)
            elif prov == "gemini":
                result = enrich_with_gemini(brand_name, api_key, model)
            else:
                continue
            
            if result.get("us_presence") != "Error":
                return result, prov
                
        except Exception as e:
            console.print(f"[yellow]  {prov} failed: {str(e)[:50]}[/yellow]")
            continue
    
    return {
        "brand": brand_name,
        "website": "",
        "us_presence": "Error",
        "has_student_discount": "Error",
        "discount_url": "",
        "verification_provider": "Error",
        "priority": "Error",
        "notes": "All providers failed"
    }, "none"


def generate_linkedin_url(brand_name: str) -> str:
    """Generate LinkedIn search URL for marketing contacts."""
    import urllib.parse
    query = f"{brand_name} VP Marketing Director Marketing CMO Head of Partnerships"
    return f"https://www.linkedin.com/search/results/people/?keywords={urllib.parse.quote(query)}"


def display_results(results: list, providers_used: dict):
    """Display results in a formatted table."""
    table = Table(title="Pion Restaurant Lead Enrichment Results", show_lines=True)
    
    table.add_column("Brand", style="cyan", no_wrap=True)
    table.add_column("US", width=8)
    table.add_column("Discount", width=10)
    table.add_column("Provider", width=14)
    table.add_column("Priority", width=12)
    table.add_column("Source", width=10, style="dim")
    
    priority_colors = {
        "High": "green",
        "Medium": "yellow", 
        "Already Partner": "blue",
        "Low": "dim",
        "Error": "red"
    }
    
    for r in results:
        priority = r.get("priority", "Unknown")
        priority_style = priority_colors.get(priority, "white")
        brand = r.get("brand", "")
        
        table.add_row(
            brand,
            r.get("us_presence", ""),
            r.get("has_student_discount", ""),
            r.get("verification_provider", "")[:14],
            f"[{priority_style}]{priority}[/{priority_style}]",
            providers_used.get(brand, "")[:10]
        )
    
    console.print(table)
    
    # Summary
    high = sum(1 for r in results if r.get("priority") == "High")
    medium = sum(1 for r in results if r.get("priority") == "Medium")
    already = sum(1 for r in results if r.get("priority") == "Already Partner")
    
    console.print(f"\n[bold]Summary:[/bold]")
    console.print(f"  [green]High priority:[/green] {high}")
    console.print(f"  [yellow]Medium priority:[/yellow] {medium}")
    console.print(f"  [blue]Already Partner:[/blue] {already}")
    
    # Cost estimate
    provider_counts = {}
    for p in providers_used.values():
        provider_counts[p] = provider_counts.get(p, 0) + 1
    
    config = load_config()
    total_cost = 0
    for prov, count in provider_counts.items():
        cost = config.get("providers", {}).get(prov, {}).get("cost_per_lead", 0.01)
        total_cost += cost * count
    
    console.print(f"\n[dim]Estimated API cost: ${total_cost:.2f}[/dim]")


def save_results(results: list, output_path: str):
    """Save results to CSV file."""
    fieldnames = [
        "Brand", "Website", "US Presence", "Has Student Discount", 
        "Discount URL", "Verification Provider", "LinkedIn Search", 
        "Priority", "Notes"
    ]
    
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        
        for r in results:
            writer.writerow({
                "Brand": r.get("brand", ""),
                "Website": r.get("website", ""),
                "US Presence": r.get("us_presence", ""),
                "Has Student Discount": r.get("has_student_discount", ""),
                "Discount URL": r.get("discount_url", ""),
                "Verification Provider": r.get("verification_provider", ""),
                "LinkedIn Search": generate_linkedin_url(r.get("brand", "")),
                "Priority": r.get("priority", ""),
                "Notes": r.get("notes", "")
            })
    
    console.print(f"\n[green]✓ Results saved to:[/green] {output_path}")


def load_brands_from_csv(filepath: str) -> list:
    """Load brand names from a CSV file."""
    brands = []
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        for row in reader:
            if row and row[0].strip():
                if row[0].lower() in ['brand', 'name', 'company', 'restaurant']:
                    continue
                brands.append(row[0].strip())
    return brands


def process_brands(brands: list, config: dict, provider: Optional[str] = None):
    """Process a list of brands and display/save results."""
    results = []
    providers_used = {}
    
    # Show which provider(s) we'll use
    if provider:
        console.print(f"[cyan]Using provider: {provider}[/cyan]")
    else:
        console.print(f"[cyan]Waterfall: {' → '.join(config.get('waterfall_order', []))}[/cyan]")
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("Researching brands...", total=len(brands))
        
        for brand in brands:
            progress.update(task, description=f"Researching: {brand}")
            result, prov_used = enrich_brand(brand, config, provider)
            results.append(result)
            providers_used[brand] = prov_used
            progress.advance(task)
    
    console.print()
    display_results(results, providers_used)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = f"pion_leads_{timestamp}.csv"
    save_results(results, output_path)
    
    # Show top priorities
    high_priority = [r for r in results if r.get("priority") == "High"]
    if high_priority:
        console.print(f"\n[bold green]🎯 Top targets:[/bold green]")
        for r in high_priority:
            console.print(f"  • {r['brand']}: {r.get('verification_provider', '')} - {r.get('notes', '')[:60]}")


def interactive_mode(config: dict, provider: Optional[str] = None):
    """Run in interactive mode."""
    console.print(Panel.fit(
        "[bold cyan]Pion Restaurant Lead Enricher[/bold cyan]\n\n"
        "Enter restaurant brand names to research.\n"
        "Type 'done' when finished, 'quit' to exit.",
        title="Welcome"
    ))
    
    # Show provider status
    available = []
    for name, settings in config.get("providers", {}).items():
        if settings.get("enabled") and get_api_key(name, config):
            available.append(f"{name} (${settings.get('cost_per_lead', 0):.3f}/lead)")
    
    if not available:
        console.print("[red]No providers configured! Run with --config to set up.[/red]")
        return
    
    console.print(f"[dim]Available providers: {', '.join(available)}[/dim]")
    
    brands = []
    console.print("\n[bold]Enter brand names (one per line, 'done' to process):[/bold]")
    
    while True:
        try:
            brand = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
            
        if brand.lower() == 'quit':
            return
        if brand.lower() == 'done':
            break
        if brand:
            brands.append(brand)
    
    if brands:
        process_brands(brands, config, provider)


def main():
    parser = argparse.ArgumentParser(
        description="Pion Restaurant Lead Enricher - Multi-Provider Edition",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python enricher.py                              # Interactive mode
    python enricher.py brands.csv                   # Process CSV
    python enricher.py --provider perplexity        # Use specific provider
    python enricher.py --config                     # Configure API keys
    
Providers (by cost):
    perplexity   $0.005/lead   Cheapest, search-native
    anthropic    $0.015/lead   Claude with web search
    openai       $0.025/lead   GPT-4o with web search
    gemini       $0.010/lead   Gemini Pro
        """
    )
    parser.add_argument('input', nargs='*', help='CSV file or brand names')
    parser.add_argument('--provider', '-p', choices=['anthropic', 'openai', 'perplexity', 'gemini'],
                        help='Use specific provider instead of waterfall')
    parser.add_argument('--config', '-c', action='store_true', 
                        help='Configure API keys and settings')
    parser.add_argument('--show-config', action='store_true',
                        help='Show current configuration')
    
    args = parser.parse_args()
    
    # Configuration mode
    if args.config:
        configure_interactive()
        return
    
    config = load_config()
    
    # Show config mode
    if args.show_config:
        console.print(json.dumps(config, indent=2, default=str))
        return
    
    # Check if any provider is available
    has_provider = False
    for name in config.get("waterfall_order", []):
        if get_api_key(name, config) and config.get("providers", {}).get(name, {}).get("enabled"):
            has_provider = True
            break
    
    if not has_provider:
        console.print("[yellow]No API keys configured.[/yellow]")
        console.print("Run [bold]python enricher.py --config[/bold] to set up providers.")
        console.print("\nOr set environment variables:")
        console.print("  export PERPLEXITY_API_KEY=your_key  # Cheapest")
        console.print("  export ANTHROPIC_API_KEY=your_key")
        console.print("  export OPENAI_API_KEY=your_key")
        console.print("  export GEMINI_API_KEY=your_key")
        return
    
    # Process input
    if not args.input:
        interactive_mode(config, args.provider)
    elif len(args.input) == 1 and args.input[0].endswith('.csv'):
        filepath = args.input[0]
        if not Path(filepath).exists():
            console.print(f"[red]File not found: {filepath}[/red]")
            sys.exit(1)
        brands = load_brands_from_csv(filepath)
        console.print(f"[cyan]Loaded {len(brands)} brands from {filepath}[/cyan]")
        process_brands(brands, config, args.provider)
    elif len(args.input) == 1 and ',' in args.input[0]:
        brands = [b.strip() for b in args.input[0].split(',') if b.strip()]
        process_brands(brands, config, args.provider)
    else:
        brands = [b.strip() for b in args.input if b.strip()]
        process_brands(brands, config, args.provider)


if __name__ == "__main__":
    main()
