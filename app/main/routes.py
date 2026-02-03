from flask import render_template, flash, redirect, url_for, request, session, jsonify, abort
from flask_login import login_user, logout_user, current_user, login_required
from . import bp
from app import db, oauth
from app.models import (
    User, Parametros, Custo, RegistroCusto,
    CategoriaCusto, CustoVariavel, LancamentoDiario,
    Faturamento, Abastecimento, TipoCombustivel
)

from .forms import LoginForm, RegistrationForm, CustoForm
from urllib.parse import urlsplit
from datetime import datetime, timedelta, date
from sqlalchemy import extract, func
from calendar import monthrange
import locale

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
    parametro = Parametros.query.first()

    if request.method == 'POST':
        if not parametro:
            flash('Cadastre os parâmetros do veículo primeiro.', 'danger')
            return redirect(url_for('main.cadastro'))

        form_type = request.form.get('form_type')
        data_str = request.form.get('data')
        data = datetime.strptime(data_str, '%Y-%m-%d').date()

        lancamento_diario = LancamentoDiario.query.filter_by(data=data, parametro_id=parametro.id).first()
        if not lancamento_diario:
            lancamento_diario = LancamentoDiario(data=data, km_rodado=0, parametro_id=parametro.id)
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

                novo_faturamento = Faturamento(
                    valor=valor,
                    tipo=tipo,
                    fonte=fonte_final,
                    lancamento_id=lancamento_diario.id
                )
                db.session.add(novo_faturamento)
                faturamentos_adicionados += 1

            flash(f'Desempenho e {faturamentos_adicionados} fonte(s) de faturamento salvos com sucesso!', 'success')

        elif form_type == 'custo':
            custo_descricoes = request.form.getlist('custoDescricao')
            custo_categorias = request.form.getlist('custoCategoria')
            new_category_names = request.form.getlist('newCategoryName')
            custo_valores = request.form.getlist('custoValor')

            custos_adicionados = 0
            for i in range(len(custo_valores)):
                valor_custo_str = custo_valores[i].strip()
                if not valor_custo_str or not custo_categorias[i]:
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
                    novo_custo_variavel = CustoVariavel(
                        descricao=descricao_custo if descricao_custo else 'Custo sem descrição',
                        valor=float(valor_custo_str),
                        categoria_id=categoria_id_final,
                        lancamento_id=lancamento_diario.id
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
        return redirect(url_for('main.custos'))

    return render_template('edit_definicao_custo.html', form=form, custo=custo, title='Editar Custo')


@bp.route("/abastecimento", methods=['GET', 'POST'])
@login_required
def abastecimento():
    parametro = Parametros.query.first()
    if not parametro:
        flash('Cadastre os parâmetros do veículo antes de lançar um abastecimento.', 'warning')
        return redirect(url_for('main.cadastro'))

    if request.method == 'POST':
        km_atual_str = request.form.get('kmAtual')
        if not km_atual_str:
            flash('O campo KM Atual é obrigatório.', 'danger')
            return redirect(url_for('main.abastecimento'))
        
        km_atual = int(km_atual_str)
        data_obj = datetime.strptime(request.form.get('data'), '%Y-%m-%d').date()
        preco_por_litro = float(request.form.get('precoPorLitro') or 0)
        litros = float(request.form.get('litros') or 0)
        custo_total = float(request.form.get('custoTotal') or 0)
        tanque_cheio = 'tanqueCheio' in request.form
        tipo_combustivel_id_str = request.form.get('tipoCombustivel')
        novo_nome_combustivel = request.form.get('newCombustivelName', '').strip()

        if not all([preco_por_litro, litros, custo_total]):
            flash('Preencha pelo menos dois dos três campos de custo (Preço/Litro, Litros, Custo Total).', 'danger')
            return redirect(url_for('main.abastecimento'))

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
        else:
            tipo_combustivel_id_final = int(tipo_combustivel_id_str)

        novo_abastecimento = Abastecimento(
            data=data_obj, km_atual=km_atual, litros=litros, preco_por_litro=preco_por_litro,
            custo_total=custo_total, tanque_cheio=tanque_cheio, tipo_combustivel_id=tipo_combustivel_id_final,
            parametro_id=parametro.id
        )
        db.session.add(novo_abastecimento)
        db.session.commit()
        recalcular_medias(parametro.id)
        db.session.commit()
        flash(f'Abastecimento de {litros:.2f}L salvo com sucesso!', 'success')
        return redirect(url_for('main.abastecimento'))

    tipos_combustivel = TipoCombustivel.query.order_by(TipoCombustivel.nome).all()
    hoje = (datetime.utcnow() - timedelta(hours=3)).strftime('%Y-%m-%d')
    historico_crescente = Abastecimento.query.filter_by(parametro_id=parametro.id).order_by(Abastecimento.data.asc(), Abastecimento.km_atual.asc()).all()

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

@bp.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dashboard():
    today = date.today()
    year = request.args.get('year', today.year, type=int)
    month = request.args.get('month', today.month, type=int)

    parametros = Parametros.query.filter_by(user_id=current_user.id).first()
    if not parametros:
        flash('Por favor, configure seus parâmetros na página de cadastro primeiro.', 'warning')
        return redirect(url_for('main.cadastro'))

    definicoes_custos = Custo.query.filter_by(user_id=current_user.id).all()
    for definicao in definicoes_custos:
        dia_vencimento_seguro = get_safe_day(definicao.dia_vencimento)
        
        try:
            data_vencimento = date(year, month, dia_vencimento_seguro)
        except ValueError:
            _, ultimo_dia = calendar.monthrange(year, month)
            data_vencimento = date(year, month, ultimo_dia)

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

    registros_custos = RegistroCusto.query.filter(
        RegistroCusto.user_id == current_user.id,
        extract('year', RegistroCusto.data_vencimento) == year,
        extract('month', RegistroCusto.data_vencimento) == month
    ).join(Custo).order_by(RegistroCusto.data_vencimento).all()

    form = RegistroCustoForm()
    if form.validate_on_submit():
        registro = RegistroCusto.query.get(form.registro_id.data)
        if registro and registro.user_id == current_user.id:
            registro.pago = form.pago.data
            registro.data_pagamento = today if registro.pago else None
            db.session.commit()
            flash('Status do custo atualizado!', 'success')
            return redirect(url_for('main.dashboard', year=year, month=month))
        else:
            flash('Registro de custo inválido.', 'danger')

    custos_fixos_pagos = sum(rc.valor for rc in registros_custos if rc.pago)
    custos_fixos_pendentes = sum(rc.valor for rc in registros_custos if not rc.pago)
    
    custos_fixos_total = db.session.query(func.sum(Custo.valor)).filter(Custo.user_id == current_user.id).scalar() or 0
    
    total_faturamento_bruto = db.session.query(func.sum(Faturamento.valor)).filter(
        Faturamento.user_id == current_user.id,
        extract('year', Faturamento.data) == year,
        extract('month', Faturamento.data) == month
    ).scalar() or 0

    total_custos_variaveis = db.session.query(func.sum(CustoVariavel.valor)).filter(
        CustoVariavel.user_id == current_user.id,
        extract('year', CustoVariavel.data) == year,
        extract('month', CustoVariavel.data) == month
    ).scalar() or 0

    lucro_liquido_parcial = total_faturamento_bruto - total_custos_variaveis - custos_fixos_pagos
    
    dias_trabalhados = db.session.query(func.count(func.distinct(Faturamento.data))).filter(
        Faturamento.user_id == current_user.id,
        extract('year', Faturamento.data) == year,
        extract('month', Faturamento.data) == month
    ).scalar() or 0

    meta_faturamento_mensal = parametros.meta_faturamento or 0
    if parametros.periodicidade_meta == 'diaria':
        meta_faturamento_mensal *= (parametros.dias_trabalho_semana or 0) * 4
    elif parametros.periodicidade_meta == 'semanal':
        meta_faturamento_mensal *= 4

    atingimento_meta_bruta = (total_faturamento_bruto / meta_faturamento_mensal * 100) if meta_faturamento_mensal > 0 else 0
    
    faturamento_liquido_parcial = total_faturamento_bruto - total_custos_variaveis
    meta_liquida = meta_faturamento_mensal
    if parametros.tipo_meta == 'liquida':
        atingimento_meta_liquida = (faturamento_liquido_parcial / meta_liquida * 100) if meta_liquida > 0 else 0
    else:
        atingimento_meta_liquida = 0

    dias_no_mes = calendar.monthrange(year, month)[1]
    dias_restantes = dias_no_mes - today.day if today.month == month and today.year == year else 0
    media_diaria_bruta = total_faturamento_bruto / dias_trabalhados if dias_trabalhados > 0 else 0
    projecao_faturamento_bruto = total_faturamento_bruto + (media_diaria_bruta * ( (parametros.dias_trabalho_semana or 0) * (dias_restantes / 7) ))
    
    media_diaria_liquida = faturamento_liquido_parcial / dias_trabalhados if dias_trabalhados > 0 else 0
    projecao_faturamento_liquido = faturamento_liquido_parcial + (media_diaria_liquida * ( (parametros.dias_trabalho_semana or 0) * (dias_restantes / 7) ))
    projecao_lucro_liquido = projecao_faturamento_liquido - custos_fixos_total

    faturamentos_diarios = db.session.query(
        extract('day', Faturamento.data).label('dia'),
        func.sum(Faturamento.valor).label('total')
    ).filter(
        Faturamento.user_id == current_user.id,
        extract('year', Faturamento.data) == year,
        extract('month', Faturamento.data) == month
    ).group_by('dia').order_by('dia').all()

    labels = [f['dia'] for f in faturamentos_diarios]
    data = [f['total'] for f in faturamentos_diarios]

    return render_template(
        'dashboard.html',
        title='Dashboard Financeiro',
        registros_custos=registros_custos,
        custos_fixos_pagos=custos_fixos_pagos,
        custos_fixos_pendentes=custos_fixos_pendentes,
        custos_fixos_total=custos_fixos_total,
        total_faturamento_bruto=total_faturamento_bruto,
        total_custos_variaveis=total_custos_variaveis,
        lucro_liquido_parcial=lucro_liquido_parcial,
        dias_trabalhados=dias_trabalhados,
        meta_faturamento_mensal=meta_faturamento_mensal,
        atingimento_meta_bruta=atingimento_meta_bruta,
        atingimento_meta_liquida=atingimento_meta_liquida,
        projecao_faturamento_bruto=projecao_faturamento_bruto,
        projecao_lucro_liquido=projecao_lucro_liquido,
        current_month=month,
        current_year=year,
        labels=labels,
        data=data,
        form=form
    )



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
    # Verifica se já existe algum abastecimento para decidir se os campos devem ser editáveis
    has_abastecimentos = Abastecimento.query.filter_by(user_id=current_user.id).first() is not None

    if request.method == 'POST':
        if 'submit_parametros' in request.form:
            if not parametro:
                parametro = Parametros(user_id=current_user.id)
                db.session.add(parametro)
            
            parametro.modelo_carro = request.form.get('modelo_carro')
            parametro.placa_carro = request.form.get('placa_carro')
            
            # Apenas atualiza KM e Consumo se for o cadastro inicial (sem abastecimentos)
            if not has_abastecimentos:
                km_str = request.form.get('km_atual')
                consumo_str = request.form.get('media_consumo')
                parametro.km_atual = int(km_str) if km_str and km_str.isdigit() else 0
                parametro.media_consumo = float(consumo_str) if consumo_str and consumo_str.replace('.', '', 1).isdigit() else 0.0

            dias_str = request.form.get('dias_trabalho_semana')
            meta_str = request.form.get('meta_faturamento')
            parametro.dias_trabalho_semana = int(dias_str) if dias_str and dias_str.isdigit() else 0
            parametro.meta_faturamento = float(meta_str) if meta_str and meta_str.replace('.', '', 1).isdigit() else 0.0
            
            parametro.periodicidade_meta = request.form.get('periodicidade_meta')
            parametro.tipo_meta = request.form.get('tipo_meta')

            try:
                db.session.commit()
                flash('Parâmetros atualizados com sucesso!', 'success')
            except Exception as e:
                db.session.rollback()
                flash(f'Erro ao salvar os parâmetros: {e}', 'danger')
            
            return redirect(url_for('main.cadastro'))

        elif 'submit' in request.form and custo_form.validate_on_submit():
            novo_custo = Custo(
                nome=custo_form.nome.data,
                valor=custo_form.valor.data,
                dia_vencimento=custo_form.dia_vencimento.data,
                observacao=custo_form.observacao.data,
                user_id=current_user.id
            )
            db.session.add(novo_custo)
            db.session.commit()
            flash('Novo custo recorrente adicionado com sucesso!', 'success')
            return redirect(url_for('main.cadastro'))

    custos = Custo.query.filter_by(user_id=current_user.id).order_by(Custo.nome).all()
    
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
    
    registro.pago = not registro.pago
    registro.data_pagamento = date.today() if registro.pago else None
    
    db.session.commit()

    flash(f'Custo \"{registro.custo.nome}\" marcado como {("pago" if registro.pago else "pendente")}.', 'success')
    
    year = registro.data_vencimento.year
    month = registro.data_vencimento.month
    return redirect(url_for('main.custos', year=year, month=month))


# --- FUNÇÃO AUXILIAR ---
def get_safe_day(year, month, day):
    """Retorna o último dia do mês se o dia for inválido."""
    _, last_day = calendar.monthrange(year, month)
    return min(day, last_day)
