import os
from flask import Flask
from flask_migrate import Migrate
from .models import db, User
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv
from flask_login import LoginManager

# Carrega as variáveis de ambiente do arquivo .env (para desenvolvimento local)
load_dotenv()

def create_app():
    app = Flask(__name__, 
              instance_relative_config=True,
              template_folder='templates', 
              static_folder='static')

    # Configuração da aplicação
    app.config.from_mapping(
        SECRET_KEY=os.getenv('SECRET_KEY', 'dev'), # Use uma chave secreta de produção!
        SQLALCHEMY_DATABASE_URI=os.getenv('DATABASE_URL') or f"sqlite:///{os.path.join(app.instance_path, 'database.db')}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        GOOGLE_CLIENT_ID=os.getenv("GOOGLE_CLIENT_ID"),
        GOOGLE_CLIENT_SECRET=os.getenv("GOOGLE_CLIENT_SECRET"),
    )

    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    # Inicializa as extensões
    db.init_app(app)
    migrate = Migrate(app, db)
    
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'main.login'
    login_manager.login_message = "Por favor, faça o login para acessar esta página."
    login_manager.login_message_category = "info"

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Configuração do OAuth
    oauth = OAuth(app)
    app.oauth = oauth
    
    # Define a URL de redirecionamento dinamicamente.
    # Para produção (PythonAnywhere), defina a variável de ambiente APP_DOMAIN.
    # Para desenvolvimento, o padrão é localhost.
    domain = os.getenv('APP_DOMAIN', f"http://localhost:{os.environ.get('PORT', 8080)}")
    google_redirect_uri = f"{domain}/authorize"

    oauth.register(
        name='google',
        client_id=app.config["GOOGLE_CLIENT_ID"],
        client_secret=app.config["GOOGLE_CLIENT_SECRET"],
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={
            'scope': 'openid email profile'
        },
        redirect_uri=google_redirect_uri
    )

    # Registra o Blueprint
    from app.main import bp as main_bp
    app.register_blueprint(main_bp, url_prefix='/')

    return app
