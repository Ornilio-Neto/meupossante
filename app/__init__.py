import os
from pathlib import Path
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()

# Caminho absoluto para a raiz do projeto
BASE_DIR = Path(__file__).resolve().parent.parent

# Inicializa extensões (sem app ainda)
db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
oauth = OAuth()

def create_app():
    app = Flask(
        __name__,
        instance_path=str(BASE_DIR / 'instance'),
        template_folder='templates',
        static_folder='static'
    )

    # Caminho absoluto correto para SQLite local (Windows/Linux)
    local_db_path = os.path.join(str(BASE_DIR), "instance", "database.db")
    local_db_path = local_db_path.replace("\\", "/")  # normaliza barras
    local_database_uri = f"sqlite:///{local_db_path}"

    # Pega DATABASE_URL do ambiente
    env_database_uri = os.getenv("DATABASE_URL")

    # Se for produção (Postgres/MySQL/etc.), usa DATABASE_URL
    # Se for SQLite mas com caminho errado (/home/...), força local_database_uri
    if env_database_uri and not env_database_uri.startswith("sqlite:////home"):
        database_uri = env_database_uri
    else:
        database_uri = local_database_uri

    # Debug: imprime o caminho do banco que está sendo usado
    print("DB URI:", database_uri)

    # Configuração da aplicação
    app.config.from_mapping(
        SECRET_KEY=os.getenv("SECRET_KEY", "dev"),
        SQLALCHEMY_DATABASE_URI=database_uri,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        GOOGLE_CLIENT_ID=os.getenv("GOOGLE_CLIENT_ID"),
        GOOGLE_CLIENT_SECRET=os.getenv("GOOGLE_CLIENT_SECRET"),
    )

    # Cria a pasta 'instance' se não existir
    try:
        (BASE_DIR / "instance").mkdir(exist_ok=True)
    except OSError:
        pass

    # Inicializa extensões
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    oauth.init_app(app)

    login_manager.login_view = "main.login"
    login_manager.login_message = "Por favor, faça o login para acessar esta página."
    login_manager.login_message_category = "info"

    # Importa modelos e blueprints dentro do contexto da app
    with app.app_context():
        from . import models
        from .main import bp as main_bp
        app.register_blueprint(main_bp)

    # Configuração do user_loader
    from .models import User
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Configuração do OAuth
    domain = os.getenv("APP_DOMAIN", f"http://localhost:{os.environ.get('PORT', 8080)}")
    google_redirect_uri = f"{domain}/authorize"

    oauth.register(
        name="google",
        client_id=app.config["GOOGLE_CLIENT_ID"],
        client_secret=app.config["GOOGLE_CLIENT_SECRET"],
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
        redirect_uri=google_redirect_uri,
    )

    return app
