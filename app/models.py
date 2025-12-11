from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Parametros(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    modelo_carro = db.Column(db.String(100), nullable=False)
    placa_carro = db.Column(db.String(20), nullable=False)
    km_atual = db.Column(db.Integer, nullable=False)
    media_consumo = db.Column(db.Float, nullable=False)
    meta_faturamento = db.Column(db.Float, nullable=False)
    periodicidade_meta = db.Column(db.String(20), nullable=False) # 'diaria', 'semanal', 'mensal'
    tipo_meta = db.Column(db.String(20), nullable=False) # 'bruta', 'liquida'
    dias_trabalho_semana = db.Column(db.Integer, nullable=False)
    
    custos_fixos = db.relationship('CustoFixo', backref='parametro', lazy=True, cascade="all, delete-orphan")
    lancamentos_diarios = db.relationship('LancamentoDiario', backref='parametro', lazy=True, cascade="all, delete-orphan")
    abastecimentos = db.relationship('Abastecimento', backref='parametro', lazy=True, cascade="all, delete-orphan")

class CustoFixo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    valor = db.Column(db.Float, nullable=False)
    parametro_id = db.Column(db.Integer, db.ForeignKey('parametros.id'), nullable=False)

class CategoriaCusto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), unique=True, nullable=False)
    custos_variaveis = db.relationship('CustoVariavel', backref='categoria', lazy=True)

class LancamentoDiario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    km_rodado = db.Column(db.Integer, nullable=False)
    faturamento = db.Column(db.Float, nullable=False)
    parametro_id = db.Column(db.Integer, db.ForeignKey('parametros.id'), nullable=False)

    custos_variaveis = db.relationship('CustoVariavel', backref='lancamento', lazy=True, cascade="all, delete-orphan")

class CustoVariavel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    descricao = db.Column(db.String(200), nullable=True)
    valor = db.Column(db.Float, nullable=False)
    categoria_id = db.Column(db.Integer, db.ForeignKey('categoria_custo.id'), nullable=False)
    lancamento_id = db.Column(db.Integer, db.ForeignKey('lancamento_diario.id'), nullable=False)

# --- NOVOS MODELOS PARA ABASTECIMENTO ---

class TipoCombustivel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(50), unique=True, nullable=False)
    abastecimentos = db.relationship('Abastecimento', backref='tipo_combustivel', lazy=True)

class Abastecimento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    km_atual = db.Column(db.Integer, nullable=False)
    litros = db.Column(db.Float, nullable=False)
    preco_por_litro = db.Column(db.Float, nullable=False)
    custo_total = db.Column(db.Float, nullable=False)
    tanque_cheio = db.Column(db.Boolean, default=False, nullable=False)
    autonomia_restante = db.Column(db.Integer, nullable=True) # Em KM, opcional
    
    tipo_combustivel_id = db.Column(db.Integer, db.ForeignKey('tipo_combustivel.id'), nullable=False)
    parametro_id = db.Column(db.Integer, db.ForeignKey('parametros.id'), nullable=False)
