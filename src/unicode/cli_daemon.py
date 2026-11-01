from typing import Annotated

import typer

from unicode.config import get_settings
from unicode.daemon.server import create_daemon_server, initialize_daemon_state
from unicode.db import close_pool, get_pool

app = typer.Typer(
    name="unicode-daemon",
    help="UniCode - Daemon host para atendimento das sessões dos alunos.",
    add_completion=False,
)


@app.command()
def run(
    endpoint: Annotated[
        str | None,
        typer.Option(
            "--socket",
            "-s",
            help="Caminho do socket Unix ou endereço tcp://host:porta.",
        ),
    ] = None,
) -> None:
    """Inicia o servidor unicode-daemon após recuperar tentativas órfãs."""
    settings = get_settings()
    target = endpoint if endpoint is not None else str(settings.daemon_socket_path)
    try:
        pool = get_pool()
        recovered, expired = initialize_daemon_state(pool=pool)
        typer.echo(
            f"unicode-daemon iniciado em {target} "
            f"(tentativas órfãs recuperadas: {recovered}, sessões expiradas limpas: {expired})"
        )
        server = create_daemon_server(target, settings=settings, pool=pool)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            typer.echo("\nEncerrando unicode-daemon...")
        finally:
            server.server_close()
    except Exception as exc:
        typer.echo(f"Erro fatal no unicode-daemon: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    finally:
        close_pool()


if __name__ == "__main__":
    app()
