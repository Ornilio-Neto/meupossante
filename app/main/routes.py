from flask import render_template, request, redirect, url_for, flash
from datetime import datetime, timedelta
import calendar
from . import bp as main
from ..models import db, Parametros, CustoFixo, CategoriaCusto, LancamentoDiario, CustoVariavel, Abastecimento, TipoCombustivel

@main.route("/", methods=['GET', 'POST'])
def index():
    parametro = Parametros.query.first()

    if request.method == 'POST':
        if not parametro:
            flash('Cadastre os parâmetros do veículo primeiro.', 'danger')
            return redirect(url_for('main.cadastro'))

        form_type = request.form.get('form_type')
        data_str = request.form.get('data')
        data = datetime.strptime(data_str, '%Y-%m-%d').date()

        # Busca ou cria o registro diário para a data informada
        lancamento_diario = LancamentoDiario.query.filter_by(data=data, parametro_id=parametro.id).first()
        if not lancamento_diario:
            lancamento_diario = LancamentoDiario(data=data, km_rodado=0, faturamento=0, parametro_id=parametro.id)
            db.session.add(lancamento_diario)

        # Se o formulário for de DESEMPENHO
        if form_type == 'desempenho':
            lancamento_diario.km_rodado = int(request.form.get('kmRodado') or 0)
            lancamento_diario.faturamento = float(request.form.get('faturamento') or 0)
            flash('Desempenho diário salvo com sucesso!', 'success')

        # Se o formulário for de CUSTO
        elif form_type == 'custo':
            custo_descricoes = request.form.getlist('custoDescricao')
            custo_categorias = request.form.getlist('custoCategoria')
            new_category_names = request.form.getlist('newCategoryName')
            custo_valores = request.form.getlist('custoValor')

            custos_adicionados = 0
            for i in range(len(custo_valores)):
                if not custo_valores[i] or not custo_descricoes[i] or not custo_categorias[i]:
                    continue

                categoria_id_final = None
                if custo_categorias[i] == 'add_new_category':
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
                else:
                    categoria_id_final = int(custo_categorias[i])

                if categoria_id_final:
                    novo_custo_variavel = CustoVariavel(
                        descricao=custo_descricoes[i],
                        valor=float(custo_valores[i]),
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

    # Lógica para GET (carregar a página)
    categorias = CategoriaCusto.query.order_by(CategoriaCusto.nome).all()
    hoje = (datetime.utcnow() - timedelta(hours=3)).strftime('%Y-%m-%d')
    return render_template('index.html', parametro=parametro, categorias=categorias, hoje=hoje)

@main.route("/abastecimento", methods=['GET', 'POST'])
def abastecimento():
    parametro = Parametros.query.first()
    if not parametro:
        flash('Cadastre os parâmetros do veículo antes de lançar um abastecimento.', 'warning')
        return redirect(url_for('main.cadastro'))

    if request.method == 'POST':
        # --- 1. CAPTURA E CONVERSÃO DOS DADOS ---
        data_obj = datetime.strptime(request.form.get('data'), '%Y-%m-%d').date()
        km_atual = int(request.form.get('kmAtual'))
        preco_por_litro = float(request.form.get('precoPorLitro') or 0)
        litros = float(request.form.get('litros') or 0)
        custo_total = float(request.form.get('custoTotal') or 0)
        tanque_cheio = 'tanqueCheio' in request.form
        autonomia_restante = int(request.form.get('autonomiaRestante') or 0)
        tipo_combustivel_id_str = request.form.get('tipoCombustivel')
        novo_nome_combustivel = request.form.get('newCombustivelName', '').strip()

        # --- 2. VALIDAÇÃO DOS DADOS ---
        if km_atual <= parametro.km_atual:
            flash(f'O KM atual ({km_atual} km) deve ser maior que o último KM registrado ({parametro.km_atual} km).', 'danger')
            return redirect(url_for('main.abastecimento'))

        # --- 3. CÁLCULO DOS CAMPOS DE CUSTO ---
        if preco_por_litro > 0 and litros > 0:
            custo_total = round(preco_por_litro * litros, 2)
        elif custo_total > 0 and preco_por_litro > 0:
            litros = round(custo_total / preco_por_litro, 2)
        elif custo_total > 0 and litros > 0:
            preco_por_litro = round(custo_total / litros, 3)
        else:
            flash('Preencha pelo menos dois dos três campos de custo (Preço/Litro, Litros, Custo Total).', 'danger')
            return redirect(url_for('main.abastecimento'))
        
        # --- 4. GERENCIAMENTO DO TIPO DE COMBUSTÍVEL ---
        tipo_combustivel_id_final = None
        nome_combustivel_final = ''
        if tipo_combustivel_id_str == 'add_new_combustivel':
            if not novo_nome_combustivel:
                flash('Digite o nome do novo tipo de combustível.', 'danger')
                return redirect(url_for('main.abastecimento'))
            
            existente = TipoCombustivel.query.filter(db.func.lower(TipoCombustivel.nome) == db.func.lower(novo_nome_combustivel)).first()
            if existente:
                tipo_combustivel_id_final = existente.id
                nome_combustivel_final = existente.nome
            else:
                novo_tipo_obj = TipoCombustivel(nome=novo_nome_combustivel)
                db.session.add(novo_tipo_obj)
                db.session.flush()
                tipo_combustivel_id_final = novo_tipo_obj.id
                nome_combustivel_final = novo_tipo_obj.nome
        else:
            tipo_combustivel_id_final = int(tipo_combustivel_id_str)
            tipo_comb_obj = TipoCombustivel.query.get(tipo_combustivel_id_final)
            nome_combustivel_final = tipo_comb_obj.nome

        # --- 5. CÁLCULO DE CONSUMO (SE TANQUE CHEIO) ---
        nova_media_calculada = None
        if tanque_cheio:
            ultimo_tanque_cheio = Abastecimento.query.filter_by(parametro_id=parametro.id, tanque_cheio=True).order_by(Abastecimento.data.desc(), Abastecimento.id.desc()).first()
            if ultimo_tanque_cheio:
                km_rodados = km_atual - ultimo_tanque_cheio.km_atual
                litros_consumidos = Abastecimento.query.with_entities(db.func.sum(Abastecimento.litros)).filter(
                    Abastecimento.parametro_id == parametro.id,
                    Abastecimento.data > ultimo_tanque_cheio.data
                ).scalar() or 0
                litros_consumidos += litros # Adiciona os litros do abastecimento atual

                if litros_consumidos > 0:
                    nova_media_calculada = km_rodados / litros_consumidos
                    parametro.media_consumo = nova_media_calculada

        # --- 6. CRIAÇÃO DO REGISTRO DE ABASTECIMENTO ---
        novo_abastecimento = Abastecimento(
            data=data_obj,
            km_atual=km_atual,
            litros=litros,
            preco_por_litro=preco_por_litro,
            custo_total=custo_total,
            tanque_cheio=tanque_cheio,
            autonomia_restante=autonomia_restante if autonomia_restante > 0 else None,
            tipo_combustivel_id=tipo_combustivel_id_final,
            parametro_id=parametro.id
        )
        db.session.add(novo_abastecimento)

        # --- 7. ATUALIZAÇÃO DO KM DO VEÍCULO ---
        parametro.km_atual = km_atual

        # --- 8. INTEGRAÇÃO COM CUSTOS VARIÁVEIS ---
        categoria_combustivel = CategoriaCusto.query.filter(db.func.lower(CategoriaCusto.nome) == 'combustível').first()
        if not categoria_combustivel:
            categoria_combustivel = CategoriaCusto(nome='Combustível')
            db.session.add(categoria_combustivel)
            db.session.flush()

        lancamento_diario = LancamentoDiario.query.filter_by(data=data_obj, parametro_id=parametro.id).first()
        if not lancamento_diario:
            lancamento_diario = LancamentoDiario(data=data_obj, km_rodado=0, faturamento=0, parametro_id=parametro.id)
            db.session.add(lancamento_diario)
        
        custo_abastecimento = CustoVariavel(
            descricao=f'Abastecimento - {nome_combustivel_final}',
            valor=custo_total,
            categoria_id=categoria_combustivel.id,
            lancamento=lancamento_diario
        )
        db.session.add(custo_abastecimento)

        # --- 9. COMMIT E FEEDBACK ---
        db.session.commit()
        
        mensagem_flash = f'Abastecimento de {litros:.2f}L (R$ {custo_total:.2f}) salvo com sucesso!'
        if nova_media_calculada:
            mensagem_flash += f' Nova média de consumo calculada: {nova_media_calculada:.2f} km/L.'
        
        flash(mensagem_flash, 'success')
        return redirect(url_for('main.dashboard'))

    tipos_combustivel = TipoCombustivel.query.order_by(TipoCombustivel.nome).all()
    hoje = (datetime.utcnow() - timedelta(hours=3)).strftime('%Y-%m-%d')
    return render_template('abastecimento.html', parametro=parametro, tipos_combustivel=tipos_combustivel, hoje=hoje)

@main.route("/dashboard")
def dashboard():
    parametro = Parametros.query.first()
    if not parametro:
        return render_template('dashboard.html', parametro=None)

    # --- Cálculos Base ---
    total_custos_fixos = sum(c.valor for c in parametro.custos_fixos)
    hoje = datetime.utcnow().date()
    dias_no_mes = calendar.monthrange(hoje.year, hoje.month)[1]
    dias_uteis_no_mes_estimado = (dias_no_mes * (parametro.dias_trabalho_semana / 7))

    # --- Cálculo da Meta Mensal Total ---
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

    # --- Desempenho Realizado no Mês ---
    primeiro_dia_mes = hoje.replace(day=1)
    lancamentos_mes = LancamentoDiario.query.filter(
        LancamentoDiario.parametro_id == parametro.id,
        LancamentoDiario.data >= primeiro_dia_mes,
        LancamentoDiario.data <= hoje
    ).all()

    faturamento_realizado_mes = sum(l.faturamento for l in lancamentos_mes)
    km_rodados_mes = sum(l.km_rodado for l in lancamentos_mes)
    custos_variaveis_mes = sum(c.valor for l in lancamentos_mes for c in l.custos_variaveis)
    
    desempenho_realizado_mes = faturamento_realizado_mes
    if parametro.tipo_meta == 'liquida':
        desempenho_realizado_mes -= custos_variaveis_mes

    # --- Cálculos para Metas e Saldos ---
    meta_diaria_base = (meta_mensal_objetivo / dias_uteis_no_mes_estimado) if dias_uteis_no_mes_estimado > 0 else 0
    dias_trabalhados_estimados_ate_ontem = (hoje.day - 1) * (parametro.dias_trabalho_semana / 7)
    desempenho_esperado_ate_ontem = meta_diaria_base * dias_trabalhados_estimados_ate_ontem
    saldo_mes = desempenho_realizado_mes - desempenho_esperado_ate_ontem
    meta_restante = meta_mensal_objetivo - desempenho_realizado_mes
    dias_uteis_restantes = (dias_no_mes - hoje.day + 1) * (parametro.dias_trabalho_semana / 7)
    meta_diaria_ajustada = (meta_restante / dias_uteis_restantes) if dias_uteis_restantes > 0 else meta_restante

    # --- Projeções para o Mês ---
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

    # --- Geração do Extrato Diário ---
    extrato_diario = []
    lancamentos_por_data = {l.data: l for l in lancamentos_mes}
    dia_corrente = hoje
    while dia_corrente >= primeiro_dia_mes:
        lancamento = lancamentos_por_data.get(dia_corrente)
        performance_dia = 0
        if lancamento:
            custos_variaveis_dia = sum(c.valor for c in lancamento.custos_variaveis)
            performance_dia = lancamento.faturamento
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
