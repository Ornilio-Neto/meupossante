from flask import render_template, flash, redirect, url_for, request, session, jsonify, abort
from flask_login import login_user, logout_user, current_user, login_required
from . import bp
from app import db, oauth
from app.models import (
    User, Parametros, Custo, RegistroCusto,
    CategoriaCusto, CustoVariavel, LancamentoDiario,
    Faturamento, Abastecimento, TipoCombustivel
)

from .forms import LoginForm, RegistrationForm, CustoForm, RegistroCustoForm
from urllib.parse import urlsplit
from datetime import datetime, timedelta, date
from sqlalchemy import extract, func
from calendar import monthrange
import locale
import calendar

# Configura o locale para Português do Brasil
locale.setlocale(locale.LC_TIME, 'pt_BR.UTF-8')

# --- ROTAS DE AUTENTICAÇÃO ---

@bp.route("/login", methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user is None or not user.check_password(form.password.data):
            flash('E-mail ou senha inválidos.', 'danger')
            return redirect(url_for('main.login'))
        
        login_user(user, remember=form.remember_me.data)
        next_page = request.args.get('next')
        return redirect(next_page or url_for('main.index'))
        
    return render_template("login.html", form=form)

@bp.route("/register", methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(email=form.email.data)
        user.set_password(form.password.data)
        user.name = form.email.data.split('@')[0]
        db.session.add(user)
        db.session.commit()
        flash('Conta criada com sucesso! Faça o login para continuar.', 'success')
        return redirect(url_for('main.login'))

    return render_template('register.html', form=form)

@bp.route("/login/google")
def login_google():
    redirect_uri = url_for('main.authorize', _external=True)
    return current_app.oauth.google.authorize_redirect(redirect_uri)

@bp.route("/authorize")
def authorize():
    token = current_app.oauth.google.authorize_access_token()
    user_info = current_app.oauth.google.get('https://www.googleapis.com/oauth2/v2/userinfo').json()
    
    google_id = str(user_info['id'])
    email = user_info['email']

    user = User.query.filter_by(email=email).first()

    if user is None:
        user = User(
            google_id=google_id,
            email=email,
            name=user_info.get('name'),
            profile_pic=user_info.get('picture')
        )
        db.session.add(user)
    else:
        user.google_id = google_id
        user.name = user.name or user_info.get('name')
        user.profile_pic = user.profile_pic or user_info.get('picture')
    
    db.session.commit()
    login_user(user, remember=True)
    return redirect(url_for('main.index'))

@bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Você foi desconectado.", "info")
    return redirect(url_for('main.login'))

# --- ROTAS DA APLICAÇÃO ---

@bp.route("/", methods=['GET', 'POST'])
@login_required
def index():
    # CORREÇÃO: Buscar o parâmetro associado ao usuário logado, não o primeiro do BD.
    parametro = current_user.parametros

    if request.method == 'POST':
        if not parametro:
            flash('Cadastre os parâmetros do veículo primeiro.', 'danger')
            return redirect(url_for('main.cadastro'))

        form_type = request.form.get('form_type')
        data_str = request.form.get('data')
        data = datetime.strptime(data_str, '%Y-%m-%d').date()

        # A consulta agora também filtra pelo ID do usuário para garantir que estamos editando o registro certo.
        lancamento_diario = LancamentoDiario.query.filter_by(data=data, user_id=current_user.id).first()
        if not lancamento_diario:
            # CORREÇÃO: Adicionar user_id e parametro_id ao criar um novo LancamentoDiario.
            lancamento_diario = LancamentoDiario(
                data=data,
                km_rodado=0,
                parametro_id=parametro.id,
                user_id=current_user.id  # Atribui o ID do usuário logado
            )
            db.session.add(lancamento_diario)
            db.session.flush() 

        if form_type == 'desempenho':
            km_adicional = int(request.form.get('kmRodado') or 0)
            lancamento_diario.km_rodado += km_adicional
            
            valores = request.form.getlist('faturamentoValor')
            tipos = request.form.getlist('faturamentoTipo')
            fontes = request.form.getlist('faturamentoFonte')
            fontes_outro = request.form.getlist('faturamentoFonteOutro')

            faturamentos_adicionados = 0
            for i in range(len(valores)):
                valor_str = valores[i].strip()
                if not valor_str or float(valor_str) <= 0:
                    continue
                
                valor = float(valor_str)
                tipo = tipos[i]
                
                fonte_final = 'N/A'
                if tipo == 'App':
                    fonte_selecionada = fontes[i]
                    if fonte_selecionada == 'Outro':
                        fonte_customizada = fontes_outro[i].strip()
                        fonte_final = fonte_customizada if fonte_customizada else 'Outro'
                    else:
                        fonte_final = fonte_selecionada
                else: 
                    fonte_final = 'Espécie'

                # CORREÇÃO: Adicionar user_id e data ao Faturamento.
                novo_faturamento = Faturamento(
                    valor=valor,
                    tipo=tipo,
                    fonte=fonte_final,
                    lancamento_id=lancamento_diario.id,
                    user_id=current_user.id,
                    data=data
                )
                db.session.add(novo_faturamento)
                faturamentos_adicionados += 1

            if km_adicional > 0 and faturamentos_adicionados > 0:
                flash(f'Desempenho e {faturamentos_adicionados} fonte(s) de faturamento salvos com sucesso!', 'success')
            elif faturamentos_adicionados > 0:
                flash(f'{faturamentos_adicionados} fonte(s) de faturamento salvas com sucesso!', 'success')
            elif km_adicional > 0:
                flash('Quilometragem salva com sucesso!', 'success')
            else:
                flash('Nenhum dado novo para salvar.', 'info')

        elif form_type == 'custo':
            custo_descricoes = request.form.getlist('custoDescricao')
            custo_categorias = request.form.getlist('custoCategoria')
            new_category_names = request.form.getlist('newCategoryName')
            custo_valores = request.form.getlist('custoValor')

            custos_adicionados = 0
            for i in range(len(custo_valores)):
                valor_custo_str = custo_valores[i].strip()
                if not valor_custo_str or not custo_categorias[i] or float(valor_custo_str) <= 0:
                    continue
                
                descricao_custo = custo_descricoes[i].strip()
                categoria_id_str = custo_categorias[i]
                
                categoria_id_final = None
                if categoria_id_str == 'add_new_category':
                    nome_nova_categoria = new_category_names[i].strip()
                    if nome_nova_categoria:
                        categoria_existente = CategoriaCusto.query.filter(db.func.lower(CategoriaCusto.nome) == db.func.lower(nome_nova_categoria)).first()
                        if categoria_existente:
                            categoria_id_final = categoria_existente.id
                        else:
                            nova_categoria_obj = CategoriaCusto(nome=nome_nova_categoria)
                            db.session.add(nova_categoria_obj)
                            db.session.flush()
                            categoria_id_final = nova_categoria_obj.id
                elif categoria_id_str.isdigit():
                    categoria_id_final = int(categoria_id_str)

                if categoria_id_final:
                    # CORREÇÃO: Adicionar user_id e data ao CustoVariavel.
                    novo_custo_variavel = CustoVariavel(
                        descricao=descricao_custo if descricao_custo else 'Custo sem descrição',
                        valor=float(valor_custo_str),
                        categoria_id=categoria_id_final,
                        lancamento_id=lancamento_diario.id,
                        user_id=current_user.id,
                        data=data
                    )
                    db.session.add(novo_custo_variavel)
                    custos_adicionados += 1
            
            if custos_adicionados > 0:
                flash(f'{custos_adicionados} custo(s) salvo(s) com sucesso para o dia {data.strftime("%d/%m/%Y")}!', 'success')
            else:
                flash('Nenhum custo válido foi preenchido.', 'warning')

        db.session.commit()
        return redirect(url_for('main.index'))

    categorias = CategoriaCusto.query.order_by(CategoriaCusto.nome).all()
    hoje = (datetime.utcnow() - timedelta(hours=3)).strftime('%Y-%m-%d')
    return render_template('index.html', parametro=parametro, categorias=categorias, hoje=hoje)


@bp.route('/custos', methods=['GET', 'POST'])
@login_required
def custos():
    custo_form = CustoForm()
    if 'submit_custo' in request.form and custo_form.validate_on_submit():
        novo_custo = Custo(
            nome=custo_form.nome.data,
            valor=custo_form.valor.data,
            dia_vencimento=custo_form.dia_vencimento.data,
            observacao=custo_form.observacao.data,
            user_id=current_user.id
        )
        db.session.add(novo_custo)
        db.session.commit()
        flash('Custo recorrente adicionado com sucesso!', 'success')
        return redirect(url_for('main.custos'))

    custos = Custo.query.filter_by(user_id=current_user.id).all()
    return render_template('custos.html', title='Custos Recorrentes', form=custo_form, custos=custos)


@bp.route("/custos/delete/<int:custo_id>", methods=['GET'])
@login_required
def delete_custo(custo_id):
    custo = Custo.query.get_or_404(custo_id)
    # Adicionar verificação de permissão se necessário
    db.session.delete(custo)
    db.session.commit()
    flash('Custo excluído com sucesso.', 'success')
    return redirect(url_for('main.custos'))


@bp.route('/custos/delete_definicao/<int:custo_id>', methods=['POST'])
@login_required
def delete_definicao_custo(custo_id):
    custo = Custo.query.get_or_404(custo_id)
    db.session.delete(custo)
    db.session.commit()
    flash('Definição de custo excluída!', 'success')
    return redirect(url_for('main.cadastro'))


@bp.route('/custos/edit_definicao/<int:custo_id>', methods=['GET', 'POST'])
@login_required
def edit_definicao_custo(custo_id):
    custo = Custo.query.get_or_404(custo_id)
    if custo.user_id != current_user.id:
        abort(403)
    
    form = CustoForm(obj=custo)
    if form.validate_on_submit():
        custo.nome = form.nome.data
        custo.valor = form.valor.data
        custo.dia_vencimento = form.dia_vencimento.data
        custo.observacao = form.observacao.data
        db.session.commit()
        flash('Definição de custo atualizada com sucesso!', 'success')
        # CORREÇÃO: Redireciona para a página correta
        return redirect(url_for('main.cadastro'))

    # Se a validação falhar, renderiza o template de edição novamente
    return render_template('edit_definicao_custo.html', form=form, custo=custo, title='Editar Custo')


def _get_safe_day_for_cost(day):
    try:
        return int(day)
    except (ValueError, TypeError):
        return 1
    
def _to_float(value_str):
    """Converte string para float, tratando vírgulas e valores vazios."""
    if not value_str or not isinstance(value_str, str):
        return 0.0
    try:
        return float(value_str.replace(',', '.'))
    except (ValueError, TypeError):
        return 0.0

    

@bp.route("/abastecimento", methods=['GET', 'POST'])
@login_required
def abastecimento():
    # 1. CORREÇÃO DE SEGURANÇA: Pegar os parâmetros DO USUÁRIO LOGADO.
    parametro = current_user.parametros
    if not parametro:
        flash('Cadastre os parâmetros do veículo antes de lançar um abastecimento.', 'warning')
        return redirect(url_for('main.cadastro'))

    if request.method == 'POST':
        # Validação básica dos dados de entrada
        km_atual_str = request.form.get('kmAtual')
        if not km_atual_str or not km_atual_str.isdigit():
            flash('O campo KM Atual é obrigatório e deve ser um número.', 'danger')
            return redirect(url_for('main.abastecimento'))
        
        # 2. CORREÇÃO DE MAPEAMENTO: Usar os nomes de campo corretos do modelo (valor_litro, valor_total)
        km_atual = int(km_atual_str)
        data_obj = datetime.strptime(request.form.get('data'), '%Y-%m-%d').date()
        valor_litro = float(request.form.get('precoPorLitro', '0').replace(',', '.'))
        litros = float(request.form.get('litros', '0').replace(',', '.'))
        valor_total = float(request.form.get('custoTotal', '0').replace(',', '.'))
        tanque_cheio = 'tanqueCheio' in request.form
        
        tipo_combustivel_id_str = request.form.get('tipoCombustivel')
        novo_nome_combustivel = request.form.get('newCombustivelName', '').strip()

        if sum([valor_litro > 0, litros > 0, valor_total > 0]) < 2:
             flash('Preencha pelo menos dois dos três campos de custo (Preço/Litro, Litros, Custo Total).', 'danger')
             return redirect(url_for('main.abastecimento'))

        # Lógica para o tipo de combustível (sem alterações)
        tipo_combustivel_id_final = None
        if tipo_combustivel_id_str == 'add_new_combustivel':
            if not novo_nome_combustivel:
                flash('Digite o nome do novo tipo de combustível.', 'danger')
                return redirect(url_for('main.abastecimento'))
            
            existente = TipoCombustivel.query.filter(db.func.lower(TipoCombustivel.nome) == db.func.lower(novo_nome_combustivel)).first()
            if existente:
                tipo_combustivel_id_final = existente.id
            else:
                novo_tipo_obj = TipoCombustivel(nome=novo_nome_combustivel)
                db.session.add(novo_tipo_obj)
                db.session.flush()
                tipo_combustivel_id_final = novo_tipo_obj.id
        elif tipo_combustivel_id_str and tipo_combustivel_id_str.isdigit():
            tipo_combustivel_id_final = int(tipo_combustivel_id_str)

        # Criação do objeto com os campos corretos e associação explícita
        novo_abastecimento = Abastecimento(
            data=data_obj,
            km_atual=km_atual,
            litros=litros,
            valor_litro=valor_litro,      # Nome correto
            valor_total=valor_total,      # Nome correto
            tanque_cheio=tanque_cheio,
            tipo_combustivel_id=tipo_combustivel_id_final,
            user_id=current_user.id,      # Associação explícita e segura
            parametro_id=parametro.id     # Associação explícita e segura
        )
        db.session.add(novo_abastecimento)
        
        recalcular_medias(parametro.id) # Esta função já faz o commit
        
        flash(f'Abastecimento de {litros:.2f}L salvo com sucesso!', 'success')
        return redirect(url_for('main.abastecimento'))

    # --- Lógica GET ---
    tipos_combustivel = TipoCombustivel.query.order_by(TipoCombustivel.nome).all()
    hoje = date.today().strftime('%Y-%m-%d')
    
    # 3. CORREÇÃO DA CONSULTA: Buscar o histórico a partir do usuário logado.
    historico_crescente = current_user.abastecimentos.order_by(Abastecimento.data.asc(), Abastecimento.km_atual.asc()).all()

    # Lógica de cálculo de média (sem alterações)
    for i in range(len(historico_crescente)):
        abastecimento_atual = historico_crescente[i]
        abastecimento_atual.media_desde_anterior = None
        if i > 0:
            abastecimento_anterior = historico_crescente[i-1]
            km_rodados = abastecimento_atual.km_atual - abastecimento_anterior.km_atual
            litros_consumidos = abastecimento_atual.litros
            if litros_consumidos > 0 and km_rodados > 0:
                abastecimento_atual.media_desde_anterior = km_rodados / litros_consumidos

    historico_final = list(reversed(historico_crescente))
    
    return render_template('abastecimento.html', 
        parametro=parametro, 
        tipos_combustivel=tipos_combustivel, 
        hoje=hoje, 
        historico=historico_final
    )


@bp.route('/', methods=['GET', 'POST'])
@bp.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dashboard():
    today = date.today()
    yesterday = today - timedelta(days=1)
    year = request.args.get('year', today.year, type=int)
    month = request.args.get('month', today.month, type=int)

    parametro = current_user.parametros
    if not parametro:
        flash('Por favor, configure seus parâmetros na página de cadastro primeiro.', 'warning')
        return redirect(url_for('main.cadastro'))

    definicoes_custos_ativos = Custo.query.filter_by(user_id=current_user.id, is_active=True).all()
    for definicao in definicoes_custos_ativos:
        try:
            _, ultimo_dia = calendar.monthrange(year, month)
            dia_vencimento = min(definicao.dia_vencimento, ultimo_dia)
            data_vencimento = date(year, month, dia_vencimento)
        except (ValueError, TypeError):
            continue

        existe = RegistroCusto.query.filter_by(
            custo_id=definicao.id,
            user_id=current_user.id
        ).filter(extract('month', RegistroCusto.data_vencimento) == month, 
                 extract('year', RegistroCusto.data_vencimento) == year).first()

        if not existe:
            novo_registro = RegistroCusto(
                data_vencimento=data_vencimento,
                valor=definicao.valor,
                pago=False,
                user_id=current_user.id,
                custo_id=definicao.id
            )
            db.session.add(novo_registro)
    db.session.commit()

    registros_custos_mes = current_user.registros_custo.filter(
        extract('year', RegistroCusto.data_vencimento) == year, 
        extract('month', RegistroCusto.data_vencimento) == month
    ).join(Custo).order_by(RegistroCusto.data_vencimento).all()
    
    custos_fixos_total_mes = sum(rc.valor for rc in registros_custos_mes if rc.custo.is_active)

    faturamento_bruto_real_mes = db.session.query(func.sum(Faturamento.valor)).filter(Faturamento.user_id == current_user.id, extract('year', Faturamento.data) == year, extract('month', Faturamento.data) == month).scalar() or 0
    custos_variaveis_mes = db.session.query(func.sum(CustoVariavel.valor)).filter(CustoVariavel.user_id == current_user.id, extract('year', CustoVariavel.data) == year, extract('month', CustoVariavel.data) == month).scalar() or 0
    abastecimentos_mes = db.session.query(func.sum(Abastecimento.valor_total)).filter(Abastecimento.user_id == current_user.id, extract('year', Abastecimento.data) == year, extract('month', Abastecimento.data) == month).scalar() or 0
    custos_fixos_pagos_mes = sum(rc.valor for rc in registros_custos_mes if rc.pago)
    saldo_atual_real = faturamento_bruto_real_mes - custos_variaveis_mes - abastecimentos_mes - custos_fixos_pagos_mes

    meta_diaria_base = 0
    if (parametro.dias_trabalho_semana or 0) > 0 and parametro.meta_faturamento > 0:
        if parametro.periodicidade_meta == 'diaria': meta_diaria_base = parametro.meta_faturamento
        elif parametro.periodicidade_meta == 'semanal': meta_diaria_base = parametro.meta_faturamento / parametro.dias_trabalho_semana
        elif parametro.periodicidade_meta == 'mensal': meta_diaria_base = parametro.meta_faturamento / (parametro.dias_trabalho_semana * 4.33)

    meta_mensal_bruta = meta_diaria_base * (parametro.dias_trabalho_semana * 4) if (parametro.dias_trabalho_semana and parametro.dias_trabalho_semana > 0) else 0
    
    # ========= CORREÇÃO APLICADA AQUI =========
    # A projeção agora NÃO subtrai os custos fixos.
    projecao_lucro_operacional = meta_mensal_bruta - custos_variaveis_mes - abastecimentos_mes
    
    extrato_diario = []
    lancamentos_mes = current_user.lancamentos_diarios.filter(extract('year', LancamentoDiario.data) == year, extract('month', LancamentoDiario.data) == month).order_by(LancamentoDiario.data.desc()).all()
    for lancamento in lancamentos_mes:
        faturamento_realizado = lancamento.faturamento_total
        km_rodado = lancamento.km_rodado
        valor_km = (faturamento_realizado / km_rodado) if km_rodado > 0 else 0
        cor_km = 'danger'
        if parametro.valor_km_meta and valor_km > parametro.valor_km_meta: cor_km = 'success'
        elif parametro.valor_km_minimo and valor_km >= parametro.valor_km_minimo: cor_km = 'warning'
        extrato_diario.append({'data': lancamento.data, 'faturamento_realizado': faturamento_realizado, 'meta_esperada': meta_diaria_base, 'valor_km': valor_km, 'cor_km': cor_km})

    faturamento_ontem = db.session.query(func.sum(Faturamento.valor)).filter(Faturamento.user_id == current_user.id, Faturamento.data == (date.today() - timedelta(days=1))).scalar() or 0
    meta_ajustada_para_hoje = meta_diaria_base - (faturamento_ontem - meta_diaria_base)
    faturamento_hoje = db.session.query(func.sum(Faturamento.valor)).filter(Faturamento.user_id == current_user.id, Faturamento.data == date.today()).scalar() or 0
    meta_restante_hoje = meta_ajustada_para_hoje - faturamento_hoje

    form = RegistroCustoForm() # Necessário para o modal de pagamento, se houver

    return render_template(
        'dashboard.html',
        title='Dashboard Financeiro',
        parametro=parametro,
        meta_restante_hoje=meta_restante_hoje,
        meta_hoje_atingida=(meta_restante_hoje <= 0),
        meta_ajustada_para_hoje=meta_ajustada_para_hoje,
        meta_diaria_base=meta_diaria_base,
        faturamento_bruto_real_mes=faturamento_bruto_real_mes,
        saldo_atual_real=saldo_atual_real,
        meta_mensal_bruta=meta_mensal_bruta,
        projecao_lucro_operacional=projecao_lucro_operacional,
        extrato_diario=extrato_diario,
        registros_custos=registros_custos_mes,
        custos_fixos_total=custos_fixos_total_mes,
        current_month=month,
        current_year=year,
        form=form
    )





@bp.route('/custos/toggle_active/<int:custo_id>', methods=['POST'])
@login_required
def toggle_custo_active(custo_id):
    custo = Custo.query.get_or_404(custo_id)
    if custo.user_id != current_user.id:
        abort(403)
    
    custo.is_active = not custo.is_active
    db.session.commit()
    
    status = "ativo" if custo.is_active else "inativo"
    flash(f'O custo recorrente "{custo.nome}" foi marcado como {status}.', 'success')
    return redirect(url_for('main.cadastro'))


@bp.route("/categorias", methods=['GET', 'POST'])
@login_required
def categorias():
    if request.method == 'POST':
        nome_categoria = request.form.get('nome_categoria')
        if nome_categoria:
            existente = CategoriaCusto.query.filter_by(nome=nome_categoria).first()
            if not existente:
                nova_categoria = CategoriaCusto(nome=nome_categoria)
                db.session.add(nova_categoria)
                db.session.commit()
                flash('Categoria adicionada com sucesso!', 'success')
            else:
                flash('Essa categoria já existe.', 'warning')
        return redirect(url_for('main.categorias'))
    
    todas_categorias = CategoriaCusto.query.order_by(CategoriaCusto.nome).all()
    return render_template('categorias.html', categorias=todas_categorias)

@bp.route('/cadastro', methods=['GET', 'POST'])
@login_required
def cadastro():
    parametro = current_user.parametros
    custo_form = CustoForm()
    has_abastecimentos = Abastecimento.query.filter_by(user_id=current_user.id).first() is not None

    # Estrutura para lidar com múltiplos formulários na mesma página
    if request.method == 'POST':
        form_name = request.form.get('form_name')

        # Se o formulário de CUSTOS for enviado
        if form_name == 'custos':
            if custo_form.validate_on_submit():
                novo_custo = Custo(
                    nome=custo_form.nome.data,
                    valor=custo_form.valor.data,
                    dia_vencimento=custo_form.dia_vencimento.data,
                    observacao=custo_form.observacao.data,
                    user_id=current_user.id,
                    is_active=True
                )
                db.session.add(novo_custo)
                db.session.commit()
                flash('Novo custo recorrente adicionado com sucesso!', 'success')
                return redirect(url_for('main.cadastro'))
        
        # Se o formulário de PARÂMETROS for enviado
        elif form_name == 'parametros':
            if not parametro:
                parametro = Parametros(user_id=current_user.id)
                db.session.add(parametro)
            
            parametro.modelo_carro = request.form.get('modelo_carro')
            parametro.placa_carro = request.form.get('placa_carro')
            if not has_abastecimentos:
                parametro.km_atual = int(request.form.get('km_atual') or 0)
                parametro.media_consumo = _to_float(request.form.get('media_consumo'))

            parametro.dias_trabalho_semana = int(request.form.get('dias_trabalho_semana') or 0)
            parametro.meta_faturamento = _to_float(request.form.get('meta_faturamento'))
            parametro.valor_km_minimo = _to_float(request.form.get('valor_km_minimo'))
            parametro.valor_km_meta = _to_float(request.form.get('valor_km_meta'))
            parametro.periodicidade_meta = request.form.get('periodicidade_meta')
            parametro.tipo_meta = request.form.get('tipo_meta')
            
            db.session.commit()
            flash('Parâmetros atualizados com sucesso!', 'success')
            return redirect(url_for('main.cadastro'))

    # Para requisições GET ou se a validação falhar, renderiza a página
    custos = Custo.query.filter_by(user_id=current_user.id).order_by(Custo.is_active.desc(), Custo.nome).all()
    
    return render_template('cadastro.html', title='Cadastros e Parâmetros', 
                           parametro=parametro, custos=custos, custo_form=custo_form, 
                           is_initial_setup=(not has_abastecimentos))


def recalcular_medias(parametro_id):
    abastecimentos = Abastecimento.query.filter_by(parametro_id=parametro_id).order_by(
        Abastecimento.data, Abastecimento.km_atual
    ).all()
    parametro = Parametros.query.get(parametro_id)
    
    total_km_rodados = 0
    total_litros_consumidos = 0

    # zera médias calculadas
    for abs in abastecimentos:
        abs.media_consumo_calculada = None

    # pega apenas abastecimentos com tanque cheio
    tanques_cheios = sorted(
        [abs for abs in abastecimentos if abs.tanque_cheio],
        key=lambda x: (x.data, x.km_atual)
    )

    for i in range(len(tanques_cheios) - 1):
        inicio = tanques_cheios[i]
        fim = tanques_cheios[i+1]

        km_rodados_periodo = fim.km_atual - inicio.km_atual
        litros_consumidos_periodo = sum(
            a.litros for a in abastecimentos
            if inicio.data < a.data <= fim.data and inicio.km_atual < a.km_atual <= fim.km_atual
        )

        if litros_consumidos_periodo > 0:
            media_periodo = km_rodados_periodo / litros_consumidos_periodo
            fim.media_consumo_calculada = media_periodo
            
            total_km_rodados += km_rodados_periodo
            total_litros_consumidos += litros_consumidos_periodo

    if total_litros_consumidos > 0:
        parametro.media_consumo = total_km_rodados / total_litros_consumidos
    else:
        if len(abastecimentos) > 1:
            primeiro = abastecimentos[0]
            ultimo = abastecimentos[-1]
            km_total = ultimo.km_atual - primeiro.km_atual
            litros_total = sum(a.litros for a in abastecimentos) - primeiro.litros
            if litros_total > 0:
                parametro.media_consumo = km_total / litros_total

    if abastecimentos:
        parametro.km_atual = max(a.km_atual for a in abastecimentos)
    
    db.session.commit()


# --- TOGGLE PAGO ---
@bp.route('/custo/toggle_pago/<int:registro_id>', methods=['POST'])
@login_required
def toggle_pago(registro_id):
    registro = RegistroCusto.query.get_or_404(registro_id)
    if registro.user_id != current_user.id:
        abort(403)
    
    registro.pago = not registro.pago
    registro.data_pagamento = date.today() if registro.pago else None
    db.session.commit()

    status = "pago" if registro.pago else "pendente"
    flash(f'Custo "{registro.custo.nome}" marcado como {status}.', 'success')
    
    year = registro.data_vencimento.year
    month = registro.data_vencimento.month
    return redirect(url_for('main.dashboard', year=year, month=month))




# --- FUNÇÃO AUXILIAR ---
def get_safe_day(year, month, day):
    """Retorna o último dia do mês se o dia for inválido."""
    _, last_day = calendar.monthrange(year, month)
    return min(day, last_day)
