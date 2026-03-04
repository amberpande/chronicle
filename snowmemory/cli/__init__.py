#!/usr/bin/env python3
"""
SnowMemory CLI
Usage:
  python -m snowmemory.cli write --content "..." --agent myagent
  python -m snowmemory.cli query --text "reconciliation breaks" --agent myagent
  python -m snowmemory.cli stats --agent myagent
  python -m snowmemory.cli decay --agent myagent
  python -m snowmemory.cli verify --memory-id <id>
  python -m snowmemory.cli graph --entity ACC-4521 --agent myagent
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import json
from typing import Optional

try:
    import typer
    from rich.console import Console
    from rich.table   import Table
    from rich.panel   import Panel
    from rich         import print as rprint
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

from snowmemory import MemoryOrchestrator, MemoryConfig, MemoryEvent, QueryContext

app  = typer.Typer(help="SnowMemory — Hybrid AI Agent Memory System") if HAS_RICH else None
console = Console() if HAS_RICH else None

# Global orchestrator (lazy init)
_orchestrators = {}

def get_orchestrator(agent_id: str, config_path: Optional[str] = None) -> MemoryOrchestrator:
    if agent_id not in _orchestrators:
        if config_path:
            config = MemoryConfig.from_yaml(config_path)
            config.agent_id = agent_id
        else:
            config = MemoryConfig(agent_id=agent_id)
        _orchestrators[agent_id] = MemoryOrchestrator(config)
    return _orchestrators[agent_id]


if HAS_RICH:
    @app.command()
    def write(
        content:    str            = typer.Option(..., "--content", "-c", help="Memory content to store"),
        agent:      str            = typer.Option("default", "--agent", "-a", help="Agent ID"),
        session:    Optional[str]  = typer.Option(None, "--session", "-s"),
        domain:     Optional[str]  = typer.Option(None, "--domain", "-d"),
        config_path: Optional[str] = typer.Option(None, "--config", help="Path to YAML config"),
    ):
        """Write a new memory event."""
        m      = get_orchestrator(agent, config_path)
        result = m.write(MemoryEvent(
            content=content, agent_id=agent, session_id=session, domain=domain
        ))
        if result.written:
            console.print(Panel(
                f"[green]✓ Memory written[/green]\n"
                f"ID:        [bold]{result.memory_id}[/bold]\n"
                f"Surprise:  {result.surprise_score:.3f}\n"
                f"Novelty:   {result.novelty_score:.3f}\n"
                f"Orphan:    {result.orphan_score:.3f}\n"
                f"Threshold: {result.threshold_used:.3f}",
                title="Write Result"
            ))
        else:
            console.print(Panel(
                f"[yellow]⊘ Write skipped[/yellow]\n"
                f"Reason:    {result.reason}\n"
                f"Score:     {result.surprise_score:.3f}\n"
                f"Threshold: {result.threshold_used:.3f}",
                title="Write Result"
            ))

    @app.command()
    def query(
        text:        str            = typer.Option(..., "--text", "-t", help="Query text"),
        agent:       str            = typer.Option("default", "--agent", "-a"),
        top_k:       int            = typer.Option(5, "--top-k", "-k"),
        graph:       bool           = typer.Option(True, "--graph/--no-graph"),
        config_path: Optional[str]  = typer.Option(None, "--config"),
    ):
        """Query memories by semantic similarity."""
        m       = get_orchestrator(agent, config_path)
        ctx     = QueryContext(text=text, agent_id=agent, top_k=top_k, include_graph=graph)
        results = m.query(ctx)

        table = Table(title=f"Query Results for '{text}'", show_lines=True)
        table.add_column("#",        width=3)
        table.add_column("Type",     width=12)
        table.add_column("Domain",   width=15)
        table.add_column("Decay",    width=7)
        table.add_column("Surprise", width=9)
        table.add_column("Content",  no_wrap=False)

        for i, mem in enumerate(results, 1):
            table.add_row(
                str(i),
                mem.memory_type.value,
                mem.domain,
                f"{mem.decay_weight:.2f}",
                f"{mem.surprise_score:.2f}",
                mem.content[:120] + ("..." if len(mem.content) > 120 else ""),
            )
        console.print(table)

    @app.command()
    def stats(
        agent:       str           = typer.Option("default", "--agent", "-a"),
        config_path: Optional[str] = typer.Option(None, "--config"),
    ):
        """Show memory statistics for an agent."""
        m   = get_orchestrator(agent, config_path)
        s   = m.stats()
        console.print(Panel(
            f"Agent:      [bold]{s['agent_id']}[/bold]\n"
            f"Total:      {s['total_memories']}\n"
            f"Working:    {s['by_type'].get('WORKING', 0)}\n"
            f"Experiential: {s['by_type'].get('EXPERIENTIAL', 0)}\n"
            f"Factual:    {s['by_type'].get('FACTUAL', 0)}\n"
            f"Backend:    {s['backend']}\n"
            f"Threshold:  {s['write_threshold']:.3f}\n"
            f"Retrieval rate: {s['gate_stats'].get('retrieval_rate', 0):.1%}",
            title="Memory Stats"
        ))

    @app.command()
    def decay(
        agent:       str           = typer.Option("default", "--agent", "-a"),
        config_path: Optional[str] = typer.Option(None, "--config"),
    ):
        """Apply decay to all experiential memories (run nightly)."""
        m       = get_orchestrator(agent, config_path)
        updated = m.run_decay()
        console.print(f"[green]Decay applied to {updated} memories[/green]")

    @app.command()
    def verify(
        memory_id:   str           = typer.Option(..., "--memory-id", "-m"),
        agent:       str           = typer.Option("default", "--agent", "-a"),
        config_path: Optional[str] = typer.Option(None, "--config"),
    ):
        """Verify integrity of a memory (compliance check)."""
        m      = get_orchestrator(agent, config_path)
        report = m.verify_integrity(memory_id)
        status = "[green]✓ VALID[/green]" if report.content_hash_matches else "[red]✗ TAMPERED[/red]"
        console.print(Panel(
            f"Status:   {status}\n"
            f"ID:       {report.memory_id}\n"
            f"Written:  {report.original_write_timestamp}\n"
            f"Ops:      {report.operation_count}\n"
            f"Hash OK:  {report.content_hash_matches}",
            title="Integrity Report"
        ))

    @app.command()
    def graph_query(
        entity:      str           = typer.Option(..., "--entity", "-e"),
        agent:       str           = typer.Option("default", "--agent", "-a"),
        depth:       int           = typer.Option(2, "--depth", "-d"),
        config_path: Optional[str] = typer.Option(None, "--config"),
    ):
        """Traverse the knowledge graph for an entity."""
        m       = get_orchestrator(agent, config_path)
        results = m.graph_query(entity, agent_id=agent, depth=depth)

        if not results:
            console.print(f"[yellow]No graph relations found for '{entity}'[/yellow]")
            return

        table = Table(title=f"Graph: {entity} (depth={depth})", show_lines=True)
        table.add_column("From",      width=15)
        table.add_column("Relation",  width=18)
        table.add_column("To",        width=15)
        table.add_column("Depth",     width=5)
        table.add_column("Content",   no_wrap=False)

        for r in results[:20]:
            table.add_row(
                str(r.get("from_entity", ""))[:15],
                str(r.get("relation_type", "")),
                str(r.get("to_entity", ""))[:15],
                str(r.get("depth", "")),
                str(r.get("content", ""))[:80],
            )
        console.print(table)

    @app.command()
    def demo():
        """Run a full demo of all SnowMemory capabilities."""
        console.print(Panel("[bold cyan]SnowMemory MVP Demo[/bold cyan]", expand=False))

        m = MemoryOrchestrator(MemoryConfig(agent_id="demo_agent"))

        events = [
            ("Reconciliation break of $2.3M on account ACC-4521 for EQUITIES desk. "
             "Root cause: missing SWIFT MT950. Resolved by EOD risk team action.", "trading_control"),
            ("Policy: Any control exception exceeding $1M requires CRO sign-off within 24 hours.",
             "compliance"),
            ("Pipeline recon_daily_dag failed at extraction step. Source system unavailable.",
             "data_pipeline"),
            ("Account ACC-4521 shows recurring month-end breaks. Pattern identified: T+2 settlement mismatch.",
             "trading_control"),
            ("right now debugging step 4 of reconciliation pipeline", None),
            ("The definition of a reconciliation break: any position discrepancy between "
             "front office and back office systems exceeding agreed tolerance.", "compliance"),
        ]

        console.print("\n[bold]📝 Writing memories...[/bold]")
        for content, domain in events:
            result = m.write(MemoryEvent(content=content, agent_id="demo_agent", domain=domain))
            icon = "✓" if result.written else "⊘"
            label = "written" if result.written else f"skipped ({result.reason})"
            score = f"score={result.surprise_score:.2f}"
            console.print(f"  {icon} [{score}] {content[:60]}... → {label}")

        console.print("\n[bold]🔍 Querying: 'reconciliation breaks EQUITIES'[/bold]")
        results = m.query(QueryContext(
            text="reconciliation breaks EQUITIES",
            agent_id="demo_agent",
            top_k=3,
        ))
        for i, r in enumerate(results, 1):
            console.print(f"  {i}. [{r.memory_type.value}|{r.domain}] {r.content[:80]}...")

        console.print("\n[bold]📊 Stats[/bold]")
        s = m.stats()
        console.print(f"  Total: {s['total_memories']} | "
                      f"W:{s['by_type'].get('WORKING',0)} "
                      f"E:{s['by_type'].get('EXPERIENTIAL',0)} "
                      f"F:{s['by_type'].get('FACTUAL',0)} | "
                      f"Threshold: {s['write_threshold']:.3f}")

        console.print("\n[bold green]✓ Demo complete![/bold green]")


def main():
    if HAS_RICH:
        app()
    else:
        print("Install typer and rich: pip install typer rich")


if __name__ == "__main__":
    main()
