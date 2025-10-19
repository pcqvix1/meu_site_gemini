# app.py (Versão SSE)
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
            # 1. Tenta criar o cliente e verifica a mensagem
            try:
                client = genai.Client(api_key=current_app.config["GEMINI_API_KEY"])
            except Exception:
                return jsonify({"error": "Configuração do servidor inválida. Chave da API do Gemini não encontrada."}), 500
        
            data = request.get_json()
            msg = (data.get("message") or "").strip()
            if not msg:
                return jsonify({"error": "Mensagem vazia"}), 400 

            # 2. Atualiza o histórico do usuário (para contexto)
            history = session.get("chat_history", [])
            history.append({"role": "user", "text": msg})
            session["chat_history"] = history
            session.modified = True 

            context = ""
            for h in history[-current_app.config["MAX_TURNS"]:]:
                prefix = "Usuário:" if h["role"] == "user" else "Assistente:"
                context += f"{prefix} {h['text']}\n"

            prompt = (
                "Você é um assistente gentil e natural, com memória da conversa. "
                "Continue o diálogo de forma fluida e coerente.\n"
                f"{context}Assistente:"
            )
            
            # 3. Função Generator para SSE
            @stream_with_context
            def generate_sse():
                full_text = ""
                
                try:
                    response_stream = client.models.generate_content_stream(
                        model=current_app.config["MODEL"], 
                        contents=prompt
                    )
                    
                    for chunk in response_stream:
                        text = chunk.text
                        if text:
                            # FORMATO SSE: 'data: [texto]\n\n'
                            # Adiciona um espaço extra na frente do texto para evitar erros de parsing
                            yield f"data: {text}\n\n" 
                            full_text += text
                    
                    # 4. Finalização: Envia um evento 'end' e atualiza o histórico com a resposta completa
                    yield "event: end\ndata: \n\n"
                    
                    # Atualiza o histórico na sessão (backend)
                    current_history = session.get("chat_history", [])
                    current_history.append({"role": "assistant", "text": full_text})
                    session["chat_history"] = current_history
                    session.modified = True
                    
                except APIError as e:
                    current_app.logger.error(f"Erro na API Gemini durante stream: {e}")
                    error_message = "❌ Erro na comunicação com a IA."
                    yield f"event: error\ndata: {error_message}\n\n"
                    yield "event: end\ndata: \n\n" # Finaliza o stream

            # 5. Retorna a Resposta com mimetype SSE
            return Response(
                generate_sse(), 
                mimetype='text/event-stream',
                headers={
                    'X-Accel-Buffering': 'no',
                    'Cache-Control': 'no-cache',
                    'Connection': 'keep-alive',
                    'Content-Encoding': 'none'
                }
            )

        except Exception as e:
            current_app.logger.exception("Erro interno")
            return jsonify({"error": f"Erro interno: {e.__class__.__name__}. Consulte os logs."}), 500

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


# CRUCIAL PARA O RENDER/GUNICORN
app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=app.config["DEBUG"])