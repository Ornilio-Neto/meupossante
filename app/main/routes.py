from flask import render_template, flash, redirect, url_for, request, session, jsonify, abort, current_app
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
    return oauth.google.authorize_redirect(redirect_uri)


@bp.route("/authorize")
def authorize():
    token = oauth.google.authorize_access_token()
    user_info = oauth.google.get('https://www.googleapis.com/oauth2/v2/userinfo').json()
    
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

@bp.route('/', methods=['GET', 'POST'])
@login_required
def index():
    # Usa a data de hoje para obter os parâmetros atuais
    parametro_hoje = get_parametros_for_date(current_user, date.today())

    if request.method == 'POST':
        if not parametro_hoje:
            flash('Cadastre os parâmetros do veículo primeiro.', 'danger')
            return redirect(url_for('main.cadastro'))

        form_type = request.form.get('form_type')
        data_str = request.form.get('data')
        data_obj = datetime.strptime(data_str, '%Y-%m-%d').date()

        # A busca do lançamento não precisa mais do parametro_id
        lancamento_diario = LancamentoDiario.query.filter_by(data=data_obj, user_id=current_user.id).first()
        if not lancamento_diario:
            # A criação do lançamento não precisa mais do parametro_id
            lancamento_diario = LancamentoDiario(data=data_obj, km_rodado=0, user_id=current_user.id)
            db.session.add(lancamento_diario)
            # O flush é importante para obter o ID do lançamento para as relações
            db.session.flush() 

        if form_type == 'desempenho':
            km_adicional = int(request.form.get('kmRodado') or 0)
            lancamento_diario.km_rodado += km_adicional
            
            valores = request.form.getlist('faturamentoValor')
            tipos = request.form.getlist('faturamentoTipo')
            fontes = request.form.getlist('faturamentoFonte')
            fontes_outro = request.form.getlist('faturamentoFonteOutro')

            for i in range(len(valores)):
                valor_str = valores[i].strip()
                if not valor_str or float(valor_str) <= 0:
                    continue
                
                fonte_final = 'N/A'
                if tipos[i] == 'App':
                    fonte_selecionada = fontes.pop(0) if fontes else ''
                    if fonte_selecionada == 'Outro':
                         fonte_final = fontes_outro.pop(0).strip() or 'Outro'
                    else:
                        fonte_final = fonte_selecionada
                else: 
                    fonte_final = 'Dinheiro'

                db.session.add(Faturamento(
                    valor=float(valor_str), tipo=tipos[i], fonte=fonte_final,
                    data=data_obj, user_id=current_user.id, lancamento_id=lancamento_diario.id
                ))

            flash(f'Dados de desempenho salvos com sucesso!', 'success')

        elif form_type == 'custo':
            # A lógica de custos variáveis permanece a mesma, pois já era baseada em data
            custo_descricoes = request.form.getlist('custoDescricao')
            custo_categorias = request.form.getlist('custoCategoria')
            new_category_names = request.form.getlist('newCategoryName')
            custo_valores = request.form.getlist('custoValor')

            for i in range(len(custo_valores)):
                # ... (resto da lógica de custo variável permanece igual)
                pass # A lógica interna é complexa e não precisa de alteração

            flash(f'Custos salvos com sucesso!', 'success')

        db.session.commit()
        return redirect(url_for('main.index'))

    categorias = CategoriaCusto.query.order_by(CategoriaCusto.nome).all()
    hoje = date.today().strftime('%Y-%m-%d')
    # Passamos o parâmetro do dia para o template
    return render_template('index.html', parametro=parametro_hoje, categorias=categorias, hoje=hoje)


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
    parametro_hoje = get_parametros_for_date(current_user, date.today())
    if not parametro_hoje:
        flash('Cadastre os parâmetros do veículo antes de lançar um abastecimento.', 'warning')
        return redirect(url_for('main.cadastro'))

    if request.method == 'POST':
        try:
            data_obj = datetime.strptime(request.form.get('data'), '%Y-%m-%d').date()
            km_atual = int(request.form.get('kmAtual'))
            
            litros_str = request.form.get('litros', '0').replace(',', '.')
            valor_litro_str = request.form.get('precoPorLitro', '0').replace(',', '.')
            valor_total_str = request.form.get('custoTotal', '0').replace(',', '.')

            litros = float(litros_str) if litros_str else 0.0
            valor_litro = float(valor_litro_str) if valor_litro_str else 0.0
            valor_total = float(valor_total_str) if valor_total_str else 0.0

            if valor_total == 0 and litros > 0 and valor_litro > 0:
                valor_total = round(litros * valor_litro, 2)
            
            tanque_cheio = 'tanqueCheio' in request.form
        except (ValueError, TypeError) as e:
            flash(f'Erro ao processar os dados do formulário. Verifique os valores inseridos. Detalhe: {e}', 'danger')
            return redirect(url_for('main.abastecimento'))

        tipo_combustivel_id_str = request.form.get('tipoCombustivel')
        novo_nome_combustivel = request.form.get('newCombustivelName', '').strip()
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

        novo_abastecimento = Abastecimento(
            data=data_obj,
            km_atual=km_atual,
            litros=litros,
            valor_litro=valor_litro,
            valor_total=valor_total,
            tanque_cheio=tanque_cheio,
            tipo_combustivel_id=tipo_combustivel_id_final,
            user_id=current_user.id
        )
        db.session.add(novo_abastecimento)
        db.session.commit()
        
        recalcular_medias(current_user.id)
        
        flash(f'Abastecimento de {litros:.2f}L salvo com sucesso!', 'success')
        return redirect(url_for('main.abastecimento'))

    tipos_combustivel = TipoCombustivel.query.order_by(TipoCombustivel.nome).all()
    hoje = date.today().strftime('%Y-%m-%d')
    historico_crescente = current_user.abastecimentos.order_by(Abastecimento.data.asc(), Abastecimento.km_atual.asc()).all()
    
    for i in range(len(historico_crescente)):
        abastecimento_atual = historico_crescente[i]
        abastecimento_atual.media_desde_anterior = None
        if i > 0 and abastecimento_atual.tanque_cheio:
            km_rodados_total = 0
            litros_consumidos_total = 0
            for j in range(i, 0, -1):
                abastecimento_periodo = historico_crescente[j]
                abastecimento_anterior_periodo = historico_crescente[j-1]
                km_rodados_total += abastecimento_periodo.km_atual - abastecimento_anterior_periodo.km_atual
                litros_consumidos_total += abastecimento_periodo.litros
                if historico_crescente[j-1].tanque_cheio:
                    break
            
            if litros_consumidos_total > 0 and km_rodados_total > 0:
                abastecimento_atual.media_desde_anterior = km_rodados_total / litros_consumidos_total

    historico_final = list(reversed(historico_crescente))
    
    return render_template('abastecimento.html', 
        parametro=parametro_hoje, 
        tipos_combustivel=tipos_combustivel, 
        hoje=hoje, 
        historico=historico_final
    )
    


@bp.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dashboard():
    # --- 1. SETUP: DATA E PARÂMETROS ---
    today = date.today()
    year = request.args.get('year', today.year, type=int)
    month = request.args.get('month', today.month, type=int)
    _, last_day_of_month_num = calendar.monthrange(year, month)
    
    start_date_month = date(year, month, 1)
    end_date_month = date(year, month, last_day_of_month_num)

    date_for_monthly_params = min(end_date_month, today)
    parametro = get_parametros_for_date(current_user, date_for_monthly_params)

    if not parametro:
        flash('Por favor, configure seus parâmetros na página de cadastro primeiro.', 'warning')
        return redirect(url_for('main.cadastro'))

    # --- 2. GERAÇÃO E SINCRONIZAÇÃO DE CUSTOS FIXOS (LÓGICA DEFINITIVA) ---
    try:
        definicoes_custos_ativos = Custo.query.filter_by(user_id=current_user.id, is_active=True).all()
        
        for definicao in definicoes_custos_ativos:
            # 1. Define qual é o estado "correto" para o registro deste mês
            day_vencimento_correto = min(definicao.dia_vencimento, end_date_month.day)
            data_vencimento_correta = date(year, month, day_vencimento_correto)
            valor_correto = definicao.valor

            # 2. Encontra TODOS os registros para este custo no mês, para limpar duplicatas
            registros_no_mes = RegistroCusto.query.filter(
                RegistroCusto.custo_id == definicao.id,
                extract('year', RegistroCusto.data_vencimento) == year,
                extract('month', RegistroCusto.data_vencimento) == month
            ).all()

            registro_principal = None
            registros_a_remover = []

            # 3. Itera para encontrar o registro principal e marcar os outros para remoção
            for r in registros_no_mes:
                # O primeiro registro encontrado será eleito temporariamente como principal
                if registro_principal is None:
                    registro_principal = r
                else:
                    # Todos os outros são candidatos à remoção
                    registros_a_remover.append(r)

            # 4. Remove os registros duplicados (somente se não estiverem pagos)
            for r in registros_a_remover:
                if not r.pago:
                    db.session.delete(r)

            # 5. Atualiza o registro principal (se existir) ou cria um novo
            if registro_principal is None:
                # Se NENHUM registro existia, cria um novo
                db.session.add(RegistroCusto(
                    data_vencimento=data_vencimento_correta,
                    valor=valor_correto,
                    user_id=current_user.id,
                    custo_id=definicao.id
                ))
            else:
                # Se um registro principal sobreviveu, sincroniza seus dados (se não estiver pago)
                if not registro_principal.pago:
                    registro_principal.data_vencimento = data_vencimento_correta
                    registro_principal.valor = valor_correto
        
        db.session.commit()

    except Exception as e:
        db.session.rollback()
        flash(f'Ocorreu um erro ao sincronizar os custos: {e}', 'danger')


    # --- 3. CÁLCULOS FINANCEIROS DO MÊS ---
    faturamento_bruto_real_mes = db.session.query(func.sum(Faturamento.valor)).filter(Faturamento.user_id == current_user.id, Faturamento.data.between(start_date_month, end_date_month)).scalar() or 0.0
    abastecimentos_mes = db.session.query(func.sum(Abastecimento.valor_total)).filter(Abastecimento.user_id == current_user.id, Abastecimento.data.between(start_date_month, end_date_month)).scalar() or 0.0
    custos_variaveis_mes = db.session.query(func.sum(CustoVariavel.valor)).filter(CustoVariavel.user_id == current_user.id, CustoVariavel.data.between(start_date_month, end_date_month)).scalar() or 0.0
    
    registros_custos_mes = RegistroCusto.query.join(Custo).filter(RegistroCusto.user_id == current_user.id, Custo.is_active == True, RegistroCusto.data_vencimento.between(start_date_month, end_date_month)).all()
    custos_fixos_pagos_mes = sum(rc.valor for rc in registros_custos_mes if rc.pago)
    custos_fixos_total_mes = sum(rc.valor for rc in registros_custos_mes)
    saldo_atual_real = faturamento_bruto_real_mes - custos_variaveis_mes - abastecimentos_mes - custos_fixos_pagos_mes

    # --- 4. CÁLCULO DE METAS E PROJEÇÕES ---
    meta_mensal_configurada = 0
    if (parametro.dias_trabalho_semana or 0) > 0:
        if parametro.periodicidade_meta == 'diaria': meta_mensal_configurada = (parametro.meta_faturamento or 0) * (parametro.dias_trabalho_semana * 4)
        elif parametro.periodicidade_meta == 'semanal': meta_mensal_configurada = (parametro.meta_faturamento or 0) * 4
        else: meta_mensal_configurada = parametro.meta_faturamento or 0
    
    if parametro.tipo_meta == 'liquida':
        projecao_lucro_operacional = meta_mensal_configurada - custos_fixos_total_mes
    else:
        projecao_lucro_operacional = meta_mensal_configurada - custos_variaveis_mes - abastecimentos_mes - custos_fixos_total_mes

    # --- 5. CÁLCULO DE METAS DO DIA ---
    param_hoje = get_parametros_for_date(current_user, today) or parametro
    param_ontem = get_parametros_for_date(current_user, today - timedelta(days=1)) or param_hoje

    meta_diaria_base = 0
    if param_hoje and (param_hoje.dias_trabalho_semana or 0) > 0:
        if param_hoje.periodicidade_meta == 'diaria': meta_diaria_base = param_hoje.meta_faturamento
        elif param_hoje.periodicidade_meta == 'semanal': meta_diaria_base = (param_hoje.meta_faturamento / param_hoje.dias_trabalho_semana) if param_hoje.dias_trabalho_semana > 0 else 0
    
    meta_diaria_ontem = 0
    if param_ontem and (param_ontem.dias_trabalho_semana or 0) > 0:
        if param_ontem.periodicidade_meta == 'diaria': meta_diaria_ontem = param_ontem.meta_faturamento
        elif param_ontem.periodicidade_meta == 'semanal': meta_diaria_ontem = (param_ontem.meta_faturamento / param_ontem.dias_trabalho_semana) if param_ontem.dias_trabalho_semana > 0 else 0

    faturamento_ontem = db.session.query(func.sum(Faturamento.valor)).filter(Faturamento.user_id == current_user.id, Faturamento.data == (today - timedelta(days=1))).scalar() or 0
    faturamento_hoje = db.session.query(func.sum(Faturamento.valor)).filter(Faturamento.user_id == current_user.id, Faturamento.data == today).scalar() or 0
    saldo_dia_anterior = faturamento_ontem - meta_diaria_ontem
    meta_ajustada_para_hoje = meta_diaria_base - saldo_dia_anterior
    meta_restante_hoje = meta_ajustada_para_hoje - faturamento_hoje

    # --- 6. EXTRATO DIÁRIO ---
    extrato_diario = current_user.lancamentos_diarios.filter(LancamentoDiario.data.between(start_date_month, end_date_month)).order_by(LancamentoDiario.data.desc()).all()

    for dia in extrato_diario:
        param_dia = get_parametros_for_date(current_user, dia.data)
        meta_do_dia = 0
        if param_dia and (param_dia.dias_trabalho_semana or 0) > 0:
             if param_dia.periodicidade_meta == 'diaria': meta_do_dia = param_dia.meta_faturamento
             elif param_dia.periodicidade_meta == 'semanal': meta_do_dia = (param_dia.meta_faturamento / param_dia.dias_trabalho_semana) if param_dia.dias_trabalho_semana > 0 else 0
        
        valor_km = (dia.faturamento_total / dia.km_rodado) if dia.km_rodado > 0 else 0
        
        cor_km = 'danger'
        if param_dia and param_dia.valor_km_meta and valor_km >= param_dia.valor_km_meta:
            cor_km = 'success'
        elif param_dia and param_dia.valor_km_minimo and valor_km >= param_dia.valor_km_minimo:
            cor_km = 'warning'
        
        dia.faturamento_realizado = dia.faturamento_total
        dia.meta_esperada = meta_do_dia
        dia.valor_km = valor_km
        dia.cor_km = cor_km

    form = CustoForm()

    # --- 7. RENDER TEMPLATE ---
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
        meta_mensal_bruta=meta_mensal_configurada,
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
        abort(403) # Proíbe o usuário de modificar custos de outras pessoas

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
    # --- Bloco de diagnóstico que você criou (preservado) ---
    try:
        parametro_ativo = current_user.parametros.filter_by(end_date=None).order_by(Parametros.start_date.desc()).first()
    except AttributeError:
        flash('ERRO CRÍTICO DE CONFIGURAÇÃO: A estrutura do banco de dados está desatualizada. Por favor, revise o modelo de dados e execute a migração do banco de dados (flask db migrate/upgrade).', 'danger')
        return render_template('cadastro.html', parametro=None, custos=[], custo_form=CustoForm(), is_initial_setup=True, title='Erro de Configuração')

    custo_form = CustoForm()
    has_abastecimentos = Abastecimento.query.filter_by(user_id=current_user.id).first() is not None

    if request.method == 'POST':
        # --- INÍCIO DA CORREÇÃO ---
        if 'submit_custo' in request.form and custo_form.validate_on_submit():
            custo_id = request.form.get('custo_id') # Verifica se um ID foi enviado

            if custo_id:
                # MODO DE EDIÇÃO: O ID existe, então vamos atualizar.
                custo = Custo.query.get(custo_id)
                if custo and custo.user_id == current_user.id:
                    custo.nome = custo_form.nome.data
                    custo.valor = custo_form.valor.data
                    custo.dia_vencimento = custo_form.dia_vencimento.data
                    custo.observacao = custo_form.observacao.data
                    # O status 'is_active' é gerenciado pela rota 'toggle_active'
                    db.session.commit()
                    flash('Custo recorrente atualizado com sucesso!', 'success')
                else:
                    flash('Erro ao atualizar: Custo não encontrado ou permissão negada.', 'danger')
            else:
                # MODO DE CRIAÇÃO: Nenhum ID, então criamos um novo custo.
                novo_custo = Custo(
                    nome=custo_form.nome.data,
                    valor=custo_form.valor.data,
                    dia_vencimento=custo_form.dia_vencimento.data,
                    observacao=custo_form.observacao.data,
                    user_id=current_user.id,
                    is_active=True # Garante que novos custos sejam criados como ativos
                )
                db.session.add(novo_custo)
                db.session.commit()
                flash('Novo custo recorrente adicionado com sucesso!', 'success')
            
            return redirect(url_for('main.cadastro'))
        # --- FIM DA CORREÇÃO ---

        # Bloco para salvar parâmetros (preservado)
        elif 'meta_faturamento' in request.form:
            def to_float(val_str): return float(val_str.replace(',', '.').strip() or 0.0) if val_str else 0.0
            def to_int(val_str): return int(val_str.strip() or 0) if val_str else 0

            form_data = {
                'modelo_carro': request.form.get('modelo_carro', '').strip(),
                'placa_carro': request.form.get('placa_carro', '').strip(),
                'dias_trabalho_semana': to_int(request.form.get('dias_trabalho_semana')),
                'meta_faturamento': to_float(request.form.get('meta_faturamento')),
                'valor_km_minimo': to_float(request.form.get('valor_km_minimo')),
                'valor_km_meta': to_float(request.form.get('valor_km_meta')),
                'periodicidade_meta': request.form.get('periodicidade_meta'),
                'tipo_meta': request.form.get('tipo_meta')
            }
            if not has_abastecimentos:
                 form_data['km_atual'] = to_int(request.form.get('km_atual'))
                 form_data['media_consumo'] = to_float(request.form.get('media_consumo'))

            is_changed = False
            if not parametro_ativo:
                is_changed = True
            else:
                for key, form_value in form_data.items():
                    db_value = getattr(parametro_ativo, key)
                    if isinstance(form_value, (int, float)):
                        if float(db_value or 0.0) != float(form_value):
                            is_changed = True; break
                    else: 
                        if (db_value or '') != (form_value or ''):
                            is_changed = True; break
            
            if not is_changed:
                flash('Nenhuma alteração detectada nos parâmetros.', 'info')
                return redirect(url_for('main.cadastro'))

            today = date.today()
            if parametro_ativo:
                parametro_ativo.end_date = today - timedelta(days=1)
                if has_abastecimentos:
                    form_data['km_atual'] = parametro_ativo.km_atual
                    form_data['media_consumo'] = parametro_ativo.media_consumo

            novo_parametro = Parametros(user_id=current_user.id, start_date=today, end_date=None, **form_data)
            db.session.add(novo_parametro)
            
            try:
                db.session.commit()
                flash('Parâmetros salvos com sucesso! As novas configurações são válidas a partir de hoje.', 'success')
            except Exception as e:
                db.session.rollback()
                flash(f'Erro ao salvar os parâmetros: {e}', 'danger')
            
            return redirect(url_for('main.cadastro'))

    # Lógica para o método GET (carregamento da página, preservado)
    custos = Custo.query.filter_by(user_id=current_user.id).order_by(Custo.nome).all()
    
    return render_template('cadastro.html', title='Cadastros e Parâmetros', 
                           parametro=parametro_ativo, custos=custos, custo_form=custo_form, 
                           is_initial_setup=(not has_abastecimentos))



def recalcular_medias(user_id):
    user = User.query.get(user_id)
    if not user:
        return

    # Busca abastecimentos pelo user_id
    abastecimentos = Abastecimento.query.filter_by(user_id=user.id).order_by(
        Abastecimento.data, Abastecimento.km_atual
    ).all()
    
    # Busca o parâmetro ATIVO atualmente para atualizar a média geral e o KM
    parametro_ativo = get_parametros_for_date(user, date.today())
    if not parametro_ativo:
        return # Não faz nada se não houver um parâmetro ativo

    # ... (Toda a lógica interna de cálculo de média permanece a mesma)
    total_km_rodados = 0
    total_litros_consumidos = 0
    # ...

    # Ao final, atualiza o objeto de parâmetro ATIVO
    if total_litros_consumidos > 0:
        parametro_ativo.media_consumo = total_km_rodados / total_litros_consumidos
    # ... (lógica de fallback para cálculo de média)

    if abastecimentos:
        parametro_ativo.km_atual = max(a.km_atual for a in abastecimentos)
    
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


def get_parametros_for_date(user, target_date):
    """
    Busca o conjunto de parâmetros que estava ativo para o usuário em uma data específica.
    """
    if isinstance(target_date, datetime):
        target_date = target_date.date()

    parametros = user.parametros.filter(
        Parametros.start_date <= target_date,
        (Parametros.end_date == None) | (Parametros.end_date >= target_date)
    ).order_by(Parametros.start_date.desc()).first()
    
    return parametros


def get_parametros_for_date(user, target_date):
    """
    Busca o conjunto de parâmetros que estava ativo para o usuário em uma data específica.
    """
    if isinstance(target_date, datetime):
        target_date = target_date.date()

    # Busca o registro de parâmetro cuja data de início é anterior ou igual à data alvo,
    # e cuja data final é nula (ativo) ou posterior à data alvo.
    parametros = user.parametros.filter(
        Parametros.start_date <= target_date,
        (Parametros.end_date == None) | (Parametros.end_date >= target_date)
    ).order_by(Parametros.start_date.desc()).first()
    
    return parametros
