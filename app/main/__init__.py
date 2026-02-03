import locale
from flask import Blueprint

bp = Blueprint('main', __name__)

# Configuração de Localização para o Brasil
try:
    locale.setlocale(locale.LC_ALL, 'pt_BR.UTF-8')
except locale.Error:
    locale.setlocale(locale.LC_ALL, 'C.UTF-8') # Fallback

def format_currency(value):
    if value is None:
        return "R$ 0,00"
    return locale.currency(value, grouping=True, symbol='R$')

@bp.context_processor
def inject_format_currency():
    return dict(format_currency=format_currency)

from app.main import routes
