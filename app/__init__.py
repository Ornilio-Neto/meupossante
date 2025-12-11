import os
from flask import Flask
from flask_migrate import Migrate
from .models import db

def create_app():
    app = Flask(__name__, instance_relative_config=True)

    app.config.from_mapping(
        SECRET_KEY='dev',
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{os.path.join(app.instance_path, 'database.db')}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )

    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    # Inicializa as extensões
    db.init_app(app)
    migrate = Migrate(app, db) # Adiciona o Flask-Migrate

    # Registra o Blueprint
    from app.main import bp as main_bp
    app.register_blueprint(main_bp)

    return app
