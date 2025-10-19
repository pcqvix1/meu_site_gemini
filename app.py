# app.py
import os
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, request, jsonify, render_template, session, current_app, Response, stream_with_context
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
        raise RuntimeError("❌ Faltando GEMINI_API_KEY. Verifique as VEs no Render ou o .env local.")

    register_routes(app)
    return app


def register_routes(app):
    @app.route("/")
    def index():
        return render_template("chat.html")

    @app.route("/enviar", methods=["POST"])
    def enviar():
        try:
            # TENTA CRIAR O CLIENTE AQUI
            try:
                client = genai.Client(api_key=current_app.config["GEMINI_API_KEY"])
            except Exception:
                error_message = (
                    "❌ Configuração do servidor inválida. Chave da API do Gemini não encontrada."
                )
                return Response(error_message, status=500, mimetype='text/plain')
        
            data = request.get_json()
            msg = (data.get("message") or "").strip()
            if not msg:
                return jsonify({"error": "Mensagem vazia"}), 400 

            history = session.get("chat_history", [])
            
            history.append({"role": "user", "text": msg})

            context = ""
            for h in history[-current_app.config["MAX_TURNS"]:]:
                prefix = "Usuário:" if h["role"] == "user" else "Assistente:"
                context += f"{prefix} {h['text']}\n"

            prompt = (
                "Você é um assistente gentil e natural, com memória da conversa. "
                "Continue o diálogo de forma fluida e coerente.\n"
                f"{context}Assistente:"
            )
            
            @stream_with_context
            def generate():
                full_text = ""
                
                response_stream = client.models.generate_content_stream(
                    model=current_app.config["MODEL"], 
                    contents=prompt
                )
                
                for chunk in response_stream:
                    text = chunk.text
                    if text:
                        yield text 
                        full_text += text
                
                current_history = session.get("chat_history", [])
                
                if current_history and current_history[-1]["role"] == "user":
                    current_history.append({"role": "assistant", "text": full_text})
                else:
                    current_history.append({"role": "assistant", "text": full_text})

                session["chat_history"] = current_history
                session.modified = True

            # >> ALTERAÇÕES CRÍTICAS: Adicionando múltiplos cabeçalhos anti-buffering <<
            return Response(
                generate(), 
                mimetype='text/plain',
                headers={
                    'X-Accel-Buffering': 'no',        # Para Nginx (Render usa)
                    'Cache-Control': 'no-cache',      # Garante que não seja armazenado
                    'Connection': 'keep-alive',       # Tenta manter a conexão aberta
                    'Content-Encoding': 'none'        # Evita compressão que pode causar buffering
                }
            )
            # << FIM DA ALTERAÇÃO >>

        except APIError as e:
            current_app.logger.error(f"Erro na API Gemini: {e}")
            error_message = (
                "❌ Ocorreu um erro na comunicação com a IA (API). "
                "Pode ser um problema temporário ou a chave API pode estar incorreta no servidor."
            )
            return Response(error_message, status=502, mimetype='text/plain')

        except Exception as e:
            current_app.logger.exception("Erro interno")
            error_message = f"❌ Ocorreu um erro interno no servidor: {e.__class__.__name__}. Consulte os logs."
            return Response(error_message, status=500, mimetype='text/plain')

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


# >> CRUCIAL PARA O RENDER/GUNICORN <<
app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=app.config["DEBUG"])