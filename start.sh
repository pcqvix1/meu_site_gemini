#!/usr/bin/env bash
# ARQUIVO: start.sh
# Este comando inicia o servidor Gunicorn.
# 'app:app' significa: encontre a variável 'app' no arquivo 'app.py'
gunicorn -w 4 -b 0.0.0.0:$PORT app:app