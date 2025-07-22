"""Main CLI entry point for Arth."""

import click
from rich.console import Console
from rich.table import Table

console = Console()


@click.group()
@click.version_option(version="0.1.0")
def main():
    """Arth - Personal Finance System CLI."""
    pass


@main.command()
def status():
    """Show system status."""
    console.print("🏦 [bold green]Arth Personal Finance System[/bold green]")
    console.print()
    
    table = Table(title="System Status")
    table.add_column("Component", style="cyan")
    table.add_column("Status", style="green")
    
    table.add_row("CLI", "✅ Available")
    table.add_row("Database Models", "✅ Defined")
    table.add_row("API Server", "✅ Available")
    table.add_row("Docker", "✅ Configured")
    table.add_row("CI Pipeline", "✅ Configured")
    table.add_row("ETL Pipeline", "⏳ Not implemented")
    table.add_row("Gmail Integration", "⏳ Not implemented")
    
    console.print(table)


@main.group()
def edit():
    """Edit data manually."""
    pass


@edit.command("add-txn")
@click.option("--account", required=True, help="Account ID")
@click.option("--date", required=True, help="Transaction date (YYYY-MM-DD)")
@click.option("--amount", required=True, type=float, help="Transaction amount")
@click.option("--type", "txn_type", required=True, help="Transaction type")
@click.option("--dry-run", is_flag=True, help="Show what would be done without executing")
def add_transaction(account, date, amount, txn_type, dry_run):
    """Add a transaction manually."""
    if dry_run:
        console.print(f"[yellow]DRY RUN:[/yellow] Would add transaction:")
        console.print(f"  Account: {account}")
        console.print(f"  Date: {date}")
        console.print(f"  Amount: {amount}")
        console.print(f"  Type: {txn_type}")
    else:
        console.print("[red]Error:[/red] Manual transaction addition not yet implemented")
        console.print("This will be available in M-3")


@edit.command("update-holding")
@click.option("--id", "holding_id", required=True, help="Holding ID")
@click.option("--qty", required=True, type=float, help="New quantity")
def update_holding(holding_id, qty):
    """Update a holding quantity."""
    console.print("[red]Error:[/red] Holding updates not yet implemented")
    console.print("This will be available in M-3")


@edit.command("reprice-asset")
@click.option("--symbol", required=True, help="Asset symbol")
@click.option("--price", required=True, type=float, help="New price")
@click.option("--date", required=True, help="Price date (YYYY-MM-DD)")
def reprice_asset(symbol, price, date):
    """Update asset price."""
    console.print("[red]Error:[/red] Asset repricing not yet implemented")
    console.print("This will be available in M-3")


if __name__ == "__main__":
    main() 