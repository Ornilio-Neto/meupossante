from . import db
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin

# --- AUTH MODELS ---
class User(UserMixin, db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    google_id = db.Column(db.String(30), unique=True, nullable=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=True)
    name = db.Column(db.String(100), nullable=True)
    profile_pic = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relações centralizadas
    parametros = db.relationship('Parametros', backref='user', uselist=False, cascade="all, delete-orphan")
    custos = db.relationship('Custo', backref='user', lazy='dynamic', cascade="all, delete-orphan")
    registros_custo = db.relationship('RegistroCusto', backref='user', lazy='dynamic', cascade="all, delete-orphan")
    lancamentos_diarios = db.relationship('LancamentoDiario', backref='user', lazy='dynamic', cascade="all, delete-orphan")
    faturamentos = db.relationship('Faturamento', backref='user', lazy='dynamic', cascade="all, delete-orphan")
    custos_variaveis = db.relationship('CustoVariavel', backref='user', lazy='dynamic', cascade="all, delete-orphan")
    abastecimentos = db.relationship('Abastecimento', backref='user', lazy='dynamic', cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# --- APP MODELS ---
class Parametros(db.Model):
    __tablename__ = 'parametros'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True, nullable=False)
    modelo_carro = db.Column(db.String(100))
    placa_carro = db.Column(db.String(20))
    km_atual = db.Column(db.Integer, default=0)
    media_consumo = db.Column(db.Float, default=0.0)
    meta_faturamento = db.Column(db.Float)
    periodicidade_meta = db.Column(db.String(20))
    tipo_meta = db.Column(db.String(20))
    dias_trabalho_semana = db.Column(db.Integer)
    valor_km_minimo = db.Column(db.Float, default=0.0)
    valor_km_meta = db.Column(db.Float, default=0.0)
    # Relação com LancamentoDiario
    lancamentos_diarios = db.relationship('LancamentoDiario', backref='parametro', lazy='dynamic', cascade="all, delete-orphan")

class CategoriaCusto(db.Model):
    __tablename__ = 'categoria_custo'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), unique=True, nullable=False)
    custos_variaveis = db.relationship('CustoVariavel', backref='categoria', lazy='dynamic')

class LancamentoDiario(db.Model):
    __tablename__ = 'lancamento_diario'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    parametro_id = db.Column(db.Integer, db.ForeignKey('parametros.id'), nullable=False)
    data = db.Column(db.Date, nullable=False, index=True)
    km_rodado = db.Column(db.Integer, default=0)
    faturamentos = db.relationship('Faturamento', backref='lancamento', lazy='dynamic', cascade="all, delete-orphan")
    custos_variaveis = db.relationship('CustoVariavel', backref='lancamento', lazy='dynamic', cascade="all, delete-orphan")

    @property
    def faturamento_total(self):
        return sum(f.valor for f in self.faturamentos)

    @property
    def custos_variaveis_total(self):
        return sum(c.valor for c in self.custos_variaveis)

class Faturamento(db.Model):
    __tablename__ = 'faturamento'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    lancamento_id = db.Column(db.Integer, db.ForeignKey('lancamento_diario.id'), nullable=True)
    data = db.Column(db.Date, nullable=False, index=True)
    valor = db.Column(db.Float, nullable=False)
    tipo = db.Column(db.String(50), nullable=False)
    fonte = db.Column(db.String(100))

class CustoVariavel(db.Model):
    __tablename__ = 'custo_variavel'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    lancamento_id = db.Column(db.Integer, db.ForeignKey('lancamento_diario.id'), nullable=True)
    categoria_id = db.Column(db.Integer, db.ForeignKey('categoria_custo.id'), nullable=False)
    data = db.Column(db.Date, nullable=False, index=True)
    descricao = db.Column(db.String(200), nullable=False)
    valor = db.Column(db.Float, nullable=False)

class TipoCombustivel(db.Model):
    __tablename__ = 'tipo_combustivel'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(50), unique=True, nullable=False)
    abastecimentos = db.relationship('Abastecimento', backref='tipo_combustivel', lazy='dynamic')

class Abastecimento(db.Model):
    __tablename__ = 'abastecimento'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    parametro_id = db.Column(db.Integer, db.ForeignKey('parametros.id'), nullable=False)
    data = db.Column(db.Date, nullable=False, index=True)
    km_atual = db.Column(db.Integer, nullable=False)
    litros = db.Column(db.Float, nullable=False)
    valor_litro = db.Column(db.Float)
    valor_total = db.Column(db.Float, nullable=False)
    tanque_cheio = db.Column(db.Boolean, default=False)
    tipo_combustivel_id = db.Column(db.Integer, db.ForeignKey('tipo_combustivel.id'), nullable=True)
    media_consumo_calculada = db.Column(db.Float, nullable=True)

class Custo(db.Model):
    __tablename__ = 'custo'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    nome = db.Column(db.String(120), nullable=False)
    valor = db.Column(db.Float, nullable=False)
    dia_vencimento = db.Column(db.Integer, nullable=False)
    observacao = db.Column(db.Text, nullable=True)
    alerta_dias = db.Column(db.Integer, default=7)
    registros = db.relationship('RegistroCusto', backref='custo', lazy='dynamic', cascade="all, delete-orphan")

class RegistroCusto(db.Model):
    __tablename__ = 'registro_custo'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    custo_id = db.Column(db.Integer, db.ForeignKey('custo.id'), nullable=False, index=True)
    data_vencimento = db.Column(db.Date, nullable=False, index=True)
    valor = db.Column(db.Float, nullable=False)
    pago = db.Column(db.Boolean, default=False, nullable=False)
    data_pagamento = db.Column(db.Date, nullable=True)
    metodo_pagamento = db.Column(db.String(50), nullable=True)
    observacao = db.Column(db.Text, nullable=True)
    __table_args__ = (db.UniqueConstraint('custo_id', 'data_vencimento', name='_custo_vencimento_uc'),)
