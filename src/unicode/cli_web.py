"""CLI entrypoint to run the professor FastAPI + React web panel."""

from typing import Annotated

import typer
import uvicorn

from unicode.web.app import create_app

app = typer.Typer(
    name="unicode-web",
    help="UniCode - Servidor do Painel Web do Professor.",
    add_completion=False,
)


@app.command()
def main(
    host: Annotated[
        str,
        typer.Option("--host", help="Endereço de escuta do servidor HTTP."),
    ] = "127.0.0.1",
    port: Annotated[
        int,
        typer.Option("--port", help="Porta de escuta do servidor HTTP."),
    ] = 8000,
) -> None:
    """Inicia o servidor web do painel do professor."""
    uvicorn.run(create_app(), host=host, port=port)


if __name__ == "__main__":
    app()
