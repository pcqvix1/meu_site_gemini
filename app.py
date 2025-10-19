import os
import logging
from flask import Flask, render_template, request, Response, jsonify, stream_with_context
from dotenv import load_dotenv
import google.genai as genai
from google.genai.types import GenerateContentConfig

# ==============================
# CONFIGURAÇÃO GERAL
# ==============================
load_dotenv()


class Config:
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "chave-padrao")
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024


def setup_logging():
    """Configura logging para salvar e exibir no console (Render)."""
    log_path = os.path.join(os.path.dirname(__file__), "app.log")
    logging.basicConfig(
        filename=log_path,
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )

    # Mostra logs também no painel do Render
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    logging.getLogger().addHandler(console_handler)


# ==============================
# INICIALIZAÇÃO DO APP
# ==============================
setup_logging()
config_class = Config()
app = Flask(__name__, template_folder="templates", static_folder="static")
app.config.from_object(config_class)
app.config["TEMPLATES_AUTO_RELOAD"] = True

# ==============================
# ROTA PRINCIPAL
# ==============================
@app.route("/")
def index():
    return render_template("chat.html")


# ==============================
# ROTA DE STREAM (DIGITAÇÃO AO VIVO)
# ==============================
@app.route("/stream", methods=["POST"])
def stream():
    """Rota que envia o texto em streaming para o front-end."""
    data = request.get_json()
    user_input = data.get("prompt", "").strip()

    if not user_input:
        return jsonify({"error": "Prompt vazio"}), 400

    client = genai.Client(api_key=app.config["GEMINI_API_KEY"])
    model = app.config["GEMINI_MODEL"]

    def generate():
        try:
            full_text = ""
            for event in client.models.generate_content_stream(
                model=model,
                contents=[user_input],
                config=GenerateContentConfig(temperature=0.7)
            ):
                if event.type == "content_block_delta":
                    delta = event.delta.text
                    full_text += delta
                    yield f"data: {delta}\n\n"
            yield "data: [FIM]\n\n"
        except Exception as e:
            app.logger.error(f"Erro no stream: {str(e)}")
            yield f"data: [ERRO] {str(e)}\n\n"

    return Response(stream_with_context(generate()), content_type="text/event-stream")


# ==============================
# EXECUÇÃO LOCAL
# ==============================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
