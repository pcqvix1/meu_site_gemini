#!/usr/bin/env bash
# ARQUIVO: start.sh
# Este comando inicia o servidor Gunicorn.
# 'app:app' significa: encontre a variável 'app' no arquivo 'app.py'
gunicorn app:app --worker-class gevent --workers 1 --bind 0.0.0.0:$PORT --timeout 0 --log-level info
