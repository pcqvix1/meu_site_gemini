# app.py
import os
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, request, jsonify, render_template, session, current_app
from dotenv import load_dotenv
from google import genai
from google.genai.errors import APIError
from datetime import timedelta

# Carrega variáveis do .env
load_dotenv()

class Config:
    SECRET_KEY = os.getenv(
        "FLASK_SECRET_KEY", 
        "chave_insegura_nao_usar_em_producao_se_estiver_publicado"
)   
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    DEBUG = os.getenv("FLASK_DEBUG", "False").lower() in ("1", "true", "yes")
    PERMANENT_SESSION_LIFETIME = timedelta(hours=2)
    MAX_TURNS = 12  # quantas mensagens lembrar no histórico


def create_app(config_class=Config):
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(config_class)
    setup_logging(app)

    if not app.config["GEMINI_API_KEY"]:
        raise RuntimeError("❌ Faltando GEMINI_API_KEY no .env")

    client = genai.Client(api_key=app.config["GEMINI_API_KEY"])
    app.extensions["genai_client"] = client
    register_routes(app)
    return app


def register_routes(app):
    @app.route("/")
    def index():
        return render_template("chat.html")

    @app.route("/enviar", methods=["POST"])
    def enviar():
        try:
            data = request.get_json()
            msg = (data.get("message") or "").strip()
            if not msg:
                return jsonify({"error": "Mensagem vazia"}), 400

            # Recupera histórico
            history = session.get("chat_history", [])
            history.append({"role": "user", "text": msg})

            # Monta contexto (últimos turnos)
            context = ""
            for h in history[-app.config["MAX_TURNS"]:]:
                prefix = "Usuário:" if h["role"] == "user" else "Assistente:"
                context += f"{prefix} {h['text']}\n"

            prompt = (
                "Você é um assistente gentil e natural, com memória da conversa. "
                "Continue o diálogo de forma fluida e coerente.\n"
                f"{context}Assistente:"
            )

            client = app.extensions["genai_client"]
            response = client.models.generate_content(model=app.config["MODEL"], contents=prompt)

            # Extrai texto do Gemini
            text = None
            if hasattr(response, "candidates") and response.candidates:
                parts = response.candidates[0].content.parts
                if parts and hasattr(parts[0], "text"):
                    text = parts[0].text

            if not text:
                text = str(response)

            # Adiciona resposta ao histórico
            history.append({"role": "assistant", "text": text})
            session["chat_history"] = history
            session.modified = True

            return jsonify({"reply": text})

        except APIError as e:
            app.logger.exception("Erro API Gemini")
            return jsonify({"error": f"Erro na API Gemini: {e}"}), 502
        except Exception as e:
            app.logger.exception("Erro interno")
            return jsonify({"error": f"Erro interno: {e}"}), 500

    @app.route("/reset", methods=["POST"])
    def reset():
        session.pop("chat_history", None)
        return jsonify({"ok": True})


def setup_logging(app):
    log_level = logging.DEBUG if app.config["DEBUG"] else logging.INFO
    app.logger.setLevel(log_level)
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s"))
    app.logger.addHandler(console)
    file_handler = RotatingFileHandler("app.log", maxBytes=5_000_000, backupCount=3)
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
    app.logger.addHandler(file_handler)


if __name__ == "__main__":
    app = create_app()
    app.run(host="127.0.0.1", port=5000, debug=app.config["DEBUG"])

