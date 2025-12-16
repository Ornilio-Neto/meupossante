from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Parametros(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    modelo_carro = db.Column(db.String(100), nullable=False)
    placa_carro = db.Column(db.String(20), nullable=True)
    km_atual = db.Column(db.Integer, nullable=False)
    media_consumo = db.Column(db.Float, nullable=False)  # Média geral
    meta_faturamento = db.Column(db.Float, nullable=False)
    periodicidade_meta = db.Column(db.String(20), nullable=False, default='mensal') # mensal, semanal, diaria
    tipo_meta = db.Column(db.String(20), nullable=False, default='bruta') # liquida, bruta
    dias_trabalho_semana = db.Column(db.Integer, nullable=False, default=5)

    # Relacionamentos
    custos_fixos = db.relationship('CustoFixo', back_populates='parametro', cascade="all, delete-orphan")
    lancamentos_diarios = db.relationship('LancamentoDiario', back_populates='parametro', cascade="all, delete-orphan")
    abastecimentos = db.relationship('Abastecimento', back_populates='parametro', cascade="all, delete-orphan")

class CustoFixo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    valor = db.Column(db.Float, nullable=False)
    parametro_id = db.Column(db.Integer, db.ForeignKey('parametros.id'), nullable=False)
    parametro = db.relationship('Parametros', back_populates='custos_fixos')

class CategoriaCusto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), unique=True, nullable=False)
    custos_variaveis = db.relationship('CustoVariavel', back_populates='categoria')

class LancamentoDiario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    km_rodado = db.Column(db.Integer, nullable=False)
    faturamento = db.Column(db.Float, nullable=False)
    parametro_id = db.Column(db.Integer, db.ForeignKey('parametros.id'), nullable=False)
    
    parametro = db.relationship('Parametros', back_populates='lancamentos_diarios')
    custos_variaveis = db.relationship('CustoVariavel', back_populates='lancamento', cascade="all, delete-orphan")

class CustoVariavel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    descricao = db.Column(db.String(200), nullable=False)
    valor = db.Column(db.Float, nullable=False)
    lancamento_id = db.Column(db.Integer, db.ForeignKey('lancamento_diario.id'), nullable=False)
    categoria_id = db.Column(db.Integer, db.ForeignKey('categoria_custo.id'), nullable=False)
    
    lancamento = db.relationship('LancamentoDiario', back_populates='custos_variaveis')
    categoria = db.relationship('CategoriaCusto', back_populates='custos_variaveis')

class TipoCombustivel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(50), unique=True, nullable=False)
    abastecimentos = db.relationship('Abastecimento', back_populates='tipo_combustivel')

class Abastecimento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.Date, nullable=False)
    km_atual = db.Column(db.Integer, nullable=False)
    litros = db.Column(db.Float, nullable=False)
    preco_por_litro = db.Column(db.Float, nullable=False)
    custo_total = db.Column(db.Float, nullable=False)
    tanque_cheio = db.Column(db.Boolean, default=False)
    autonomia_restante = db.Column(db.Integer, nullable=True)
    media_consumo_calculada = db.Column(db.Float, nullable=True) # Média específica do período

    parametro_id = db.Column(db.Integer, db.ForeignKey('parametros.id'), nullable=False)
    tipo_combustivel_id = db.Column(db.Integer, db.ForeignKey('tipo_combustivel.id'), nullable=False)

    parametro = db.relationship('Parametros', back_populates='abastecimentos')
    tipo_combustivel = db.relationship('TipoCombustivel', back_populates='abastecimentos')
