from flask import render_template, request, redirect, url_for, flash, current_app
from datetime import datetime, timedelta
import calendar
import locale
from . import bp as main
from .forms import LoginForm, RegistrationForm
from ..models import db, Parametros, CustoFixo, CategoriaCusto, LancamentoDiario, CustoVariavel, Abastecimento, TipoCombustivel, Faturamento, User
from flask_login import login_user, logout_user, login_required, current_user

# Configura o locale para Português do Brasil
locale.setlocale(locale.LC_TIME, 'pt_BR.UTF-8')

# --- ROTAS DE AUTENTICAÇÃO ---

@main.route("/login", methods=['GET', 'POST'])
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

@main.route("/register", methods=['GET', 'POST'])
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

@main.route("/login/google")
def login_google():
    redirect_uri = url_for('main.authorize', _external=True)
    return current_app.oauth.google.authorize_redirect(redirect_uri)

@main.route("/authorize")
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

@main.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Você foi desconectado.", "info")
    return redirect(url_for('main.login'))

# --- ROTAS DA APLICAÇÃO ---

@main.route("/", methods=['GET', 'POST'])
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

        if form_type == 'desempenho':
            lancamento_diario.km_rodado = int(request.form.get('kmRodado') or 0)
            
            Faturamento.query.filter_by(lancamento_id=lancamento_diario.id).delete()
            
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
                else: # Se for 'Especie'
                    fonte_final = 'Espécie'

                novo_faturamento = Faturamento(
                    valor=valor,
                    tipo=tipo,
                    fonte=fonte_final,
                    lancamento=lancamento_diario
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
                        lancamento=lancamento_diario
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


@main.route("/abastecimento", methods=['GET', 'POST'])
@login_required
def abastecimento():
    parametro = Parametros.query.first()
    if not parametro:
        flash('Cadastre os parâmetros do veículo antes de lançar um abastecimento.', 'warning')
        return redirect(url_for('main.cadastro'))

    if request.method == 'POST':
        data_obj = datetime.strptime(request.form.get('data'), '%Y-%m-%d').date()
        km_atual = int(request.form.get('kmAtual'))
        preco_por_litro = float(request.form.get('precoPorLitro') or 0)
        litros = float(request.form.get('litros') or 0)
        custo_total = float(request.form.get('custoTotal') or 0)
        tanque_cheio = 'tanqueCheio' in request.form
        tipo_combustivel_id_str = request.form.get('tipoCombustivel')
        novo_nome_combustivel = request.form.get('newCombustivelName', '').strip()

        if preco_por_litro > 0 and litros > 0:
            custo_total = round(preco_por_litro * litros, 2)
        elif custo_total > 0 and preco_por_litro > 0:
            litros = round(custo_total / preco_por_litro, 2)
        elif custo_total > 0 and litros > 0:
            preco_por_litro = round(custo_total / litros, 3)
        else:
            flash('Preencha pelo menos dois dos três campos de custo (Preço/Litro, Litros, Custo Total).', 'danger')
            return redirect(url_for('main.abastecimento'))
        
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

@main.route("/dashboard")
@login_required
def dashboard():
    parametro = Parametros.query.first()
    if not parametro:
        return render_template('dashboard.html', parametro=None)

    total_custos_fixos = sum(c.valor for c in parametro.custos_fixos)
    hoje = datetime.utcnow().date()
    dias_no_mes = calendar.monthrange(hoje.year, hoje.month)[1]
    dias_uteis_no_mes_estimado = (dias_no_mes * (parametro.dias_trabalho_semana / 7))

    meta_mensal_bruta = 0
    if parametro.periodicidade_meta == 'mensal':
        meta_mensal_bruta = parametro.meta_faturamento
    elif parametro.periodicidade_meta == 'semanal':
        semanas_no_mes = dias_no_mes / 7
        meta_mensal_bruta = parametro.meta_faturamento * semanas_no_mes
    elif parametro.periodicidade_meta == 'diaria':
        if dias_uteis_no_mes_estimado > 0:
            meta_mensal_bruta = parametro.meta_faturamento * dias_uteis_no_mes_estimado
    
    meta_mensal_objetivo = meta_mensal_bruta
    if parametro.tipo_meta == 'liquida':
        meta_mensal_objetivo += total_custos_fixos 

    primeiro_dia_mes = hoje.replace(day=1)
    lancamentos_mes = LancamentoDiario.query.filter(
        LancamentoDiario.parametro_id == parametro.id,
        LancamentoDiario.data >= primeiro_dia_mes,
        LancamentoDiario.data <= hoje
    ).all()

    faturamento_realizado_mes = sum(l.faturamento_total for l in lancamentos_mes)
    km_rodados_mes = sum(l.km_rodado for l in lancamentos_mes)
    custos_variaveis_mes = sum(c.valor for l in lancamentos_mes for c in l.custos_variaveis)
    
    desempenho_realizado_mes = faturamento_realizado_mes
    if parametro.tipo_meta == 'liquida':
        desempenho_realizado_mes -= custos_variaveis_mes

    meta_diaria_base = (meta_mensal_objetivo / dias_uteis_no_mes_estimado) if dias_uteis_no_mes_estimado > 0 else 0
    dias_trabalhados_estimados_ate_ontem = (hoje.day - 1) * (parametro.dias_trabalho_semana / 7)
    desempenho_esperado_ate_ontem = meta_diaria_base * dias_trabalhados_estimados_ate_ontem
    saldo_mes = desempenho_realizado_mes - desempenho_esperado_ate_ontem
    meta_restante = meta_mensal_objetivo - desempenho_realizado_mes
    dias_uteis_restantes = (dias_no_mes - hoje.day + 1) * (parametro.dias_trabalho_semana / 7)
    meta_diaria_ajustada = (meta_restante / dias_uteis_restantes) if dias_uteis_restantes > 0 else meta_restante

    previsao_faturamento_bruto_mes = 0
    previsao_lucro_operacional_mes = 0
    dias_com_lancamento_total = db.session.query(db.func.count(db.distinct(LancamentoDiario.data))).filter(LancamentoDiario.parametro_id == parametro.id, LancamentoDiario.data >= primeiro_dia_mes, LancamentoDiario.data <= hoje).scalar() or 0
    if dias_com_lancamento_total > 0:
        faturamento_medio_diario = faturamento_realizado_mes / dias_com_lancamento_total
        previsao_faturamento_bruto_mes = faturamento_medio_diario * dias_uteis_no_mes_estimado
        custo_variavel_por_km = (custos_variaveis_mes / km_rodados_mes) if km_rodados_mes > 0 else 0
        km_medio_diario = km_rodados_mes / dias_com_lancamento_total
        previsao_km_total_mes = km_medio_diario * dias_uteis_no_mes_estimado
        previsao_custos_variaveis_mes = previsao_km_total_mes * custo_variavel_por_km
        previsao_lucro_operacional_mes = previsao_faturamento_bruto_mes - previsao_custos_variaveis_mes

    extrato_diario = []
    lancamentos_por_data = {l.data: l for l in lancamentos_mes}
    dia_corrente = hoje
    while dia_corrente >= primeiro_dia_mes:
        lancamento = lancamentos_por_data.get(dia_corrente)
        performance_dia = 0
        if lancamento:
            custos_variaveis_dia = sum(c.valor for c in lancamento.custos_variaveis)
            performance_dia = lancamento.faturamento_total
            if parametro.tipo_meta == 'liquida':
                performance_dia -= custos_variaveis_dia
        
        saldo_do_dia = performance_dia - meta_diaria_base

        extrato_diario.append({
            'data': dia_corrente,
            'performance': performance_dia,
            'meta_esperada': meta_diaria_base,
            'saldo': saldo_do_dia
        })
        dia_corrente -= timedelta(days=1)

    return render_template('dashboard.html', 
        parametro=parametro, 
        total_custos_fixos=total_custos_fixos,
        meta_diaria_ajustada=meta_diaria_ajustada,
        faturamento_realizado_mes=faturamento_realizado_mes,
        saldo_mes=saldo_mes,
        km_rodados_mes=km_rodados_mes,
        previsao_faturamento_bruto_mes=previsao_faturamento_bruto_mes,
        previsao_lucro_operacional_mes=previsao_lucro_operacional_mes,
        extrato_diario=extrato_diario,
        meta_mensal_objetivo=meta_mensal_objetivo
    )


@main.route("/categorias", methods=['GET', 'POST'])
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

@main.route("/cadastro", methods=['GET', 'POST'])
@login_required
def cadastro():
    parametro_existente = Parametros.query.first()
    if request.method == 'POST':
        parametro_alvo = parametro_existente if parametro_existente else Parametros()

        parametro_alvo.modelo_carro = request.form.get('modeloCarro')
        parametro_alvo.placa_carro = request.form.get('placaCarro')
        parametro_alvo.km_atual = int(request.form.get('kmAtual'))
        parametro_alvo.media_consumo = float(request.form.get('mediaConsumo'))
        parametro_alvo.meta_faturamento = float(request.form.get('metaFaturamento'))
        parametro_alvo.periodicidade_meta = request.form.get('periodicidadeMeta')
        parametro_alvo.tipo_meta = request.form.get('tipoMeta')
        parametro_alvo.dias_trabalho_semana = int(request.form.get('diasTrabalhoSemana'))

        if not parametro_existente:
            db.session.add(parametro_alvo)
        
        parametro_alvo.custos_fixos.clear()
        custo_nomes = request.form.getlist('custoNome')
        custo_valores = request.form.getlist('custoValor')

        for nome, valor_str in zip(custo_nomes, custo_valores):
            if nome and valor_str:
                novo_custo = CustoFixo(nome=nome, valor=float(valor_str), parametro=parametro_alvo)
                db.session.add(novo_custo)

        db.session.commit()
        flash('Parâmetros salvos com sucesso!', 'success')
        return redirect(url_for('main.dashboard'))

    return render_template('cadastro.html', parametro=parametro_existente)

def recalcular_medias(parametro_id):
    abastecimentos = Abastecimento.query.filter_by(parametro_id=parametro_id).order_by(Abastecimento.data, Abastecimento.km_atual).all()
    parametro = Parametros.query.get(parametro_id)
    
    total_km_rodados = 0
    total_litros_consumidos = 0

    for abs in abastecimentos:
        abs.media_consumo_calculada = None

    tanques_cheios = sorted([abs for abs in abastecimentos if abs.tanque_cheio], key=lambda x: (x.data, x.km_atual))

    for i in range(len(tanques_cheios) - 1):
        inicio = tanques_cheios[i]
        fim = tanques_cheios[i+1]

        km_rodados_periodo = fim.km_atual - inicio.km_atual
        
        litros_consumidos_periodo = sum(a.litros for a in abastecimentos if inicio.data < a.data <= fim.data and inicio.km_atual < a.km_atual <= fim.km_atual)

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
