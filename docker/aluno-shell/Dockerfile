FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/home/aluno \
    UNICODE_STUDENT_WORKSPACE_DIR=/home/aluno \
    UNICODE_DAEMON_SOCKET_PATH=/run/unicode/daemon.sock

RUN apt-get update && apt-get install -y --no-install-recommends \
        nano \
        vim-tiny \
        less \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -g 1000 aluno \
    && useradd -m -u 1000 -g 1000 -d /home/aluno -s /bin/bash aluno

COPY pyproject.toml CLAUDE.md /opt/unicode/
COPY src/ /opt/unicode/src/

RUN pip install --no-cache-dir /opt/unicode "pytest>=8.3.0" \
    && rm -rf /opt/unicode

RUN printf '\necho "Bem-vindo ao UniCode! Comandos disponíveis:"\necho "  unicode start <unidade>   - Sorteia ou recupera suas questões da unidade"\necho "  unicode status            - Mostra questões, tentativas e pontuação"\necho "  unicode test [questao]    - Roda os exemplos públicos localmente (sem gastar tentativa)"\necho "  unicode submit [questao]  - Submete solution.py para avaliação oficial (gasta 1 tentativa)"\necho ""\n' >> /etc/bash.bashrc

WORKDIR /home/aluno
USER 1000:1000

ENTRYPOINT ["/bin/bash"]
