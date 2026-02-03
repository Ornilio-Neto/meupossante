from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, IntegerField, FloatField, DateField, TextAreaField, SelectField, HiddenField
from wtforms.validators import DataRequired, Email, EqualTo, ValidationError, NumberRange, Optional
from app.models import User

class LoginForm(FlaskForm):
    email = StringField('E-mail', validators=[DataRequired(), Email()])
    password = PasswordField('Senha', validators=[DataRequired()])
    remember_me = BooleanField('Lembrar-me')
    submit = SubmitField('Entrar')

class RegistrationForm(FlaskForm):
    email = StringField('E-mail', validators=[DataRequired(), Email()])
    password = PasswordField('Senha', validators=[DataRequired()])
    password2 = PasswordField(
        'Repita a Senha', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Registrar')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user is not None:
            raise ValidationError('Este e-mail já está sendo utilizado.')

class CustoForm(FlaskForm):
    nome = StringField('Nome do Custo', validators=[DataRequired()])
    valor = FloatField('Valor Padrão (R$)', validators=[DataRequired(), NumberRange(min=0)])
    dia_vencimento = IntegerField('Dia do Vencimento (1-31)', validators=[DataRequired(), NumberRange(min=1, max=31)])
    alerta_dias = IntegerField('Alerta (dias antes)', default=7, validators=[DataRequired(), NumberRange(min=0)])
    observacao = TextAreaField('Observações', validators=[Optional()])
    submit = SubmitField('Salvar Custo')

class RegistroCustoForm(FlaskForm):
    registro_id = HiddenField('Registro ID', validators=[DataRequired()])
    pago = BooleanField('Pago')
    submit = SubmitField('Atualizar')
