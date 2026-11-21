"""Fornada: aplicativo na internet (Streamlit).
O gerente usa pelo navegador; o cálculo roda no servidor."""
import io, os, hashlib, datetime as dt
import numpy as np, pandas as pd, streamlit as st
import motor

st.set_page_config(page_title='Fornada', layout='wide')
st.markdown("""<style>
html, body, [class*="css"] {font-size:17px}
h1 {color:#0B1F5C} h2, h3 {color:#0B1F5C}
div[data-testid="stMetricValue"] {font-size:30px; font-weight:700}
div[data-testid="stMetricLabel"] p {font-size:15px}
.stTabs [data-baseweb="tab"] p {font-size:17px; font-weight:600}
.nota {background:#EEF2F8; border-left:5px solid #0B1F5C; padding:10px 14px; border-radius:4px; margin:6px 0 12px}
.alerta {background:#FFF4E0; border-left:5px solid #C77700; padding:10px 14px; border-radius:4px; margin:6px 0 12px}
</style>""", unsafe_allow_html=True)

AQUI = os.path.dirname(os.path.abspath(__file__))
DEMO = next((p for p in (os.path.join(AQUI, 'dados', 'Fornada_base_ficticia.xlsx'), os.path.join(AQUI, 'Fornada_base_ficticia.xlsx')) if os.path.exists(p)), '')
FERIADOS = {dt.date(2026, 11, 2): 'Finados', dt.date(2026, 11, 15): 'Proclamação da República',
            dt.date(2026, 11, 20): 'Consciência Negra', dt.date(2026, 12, 25): 'Natal',
            dt.date(2027, 1, 1): 'Confraternização Universal'}


def br(v, nd=0):
    if v is None or (isinstance(v, float) and np.isnan(v)): return '–'
    s = f'{v:,.{nd}f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    return s


def rs(v): return 'R$ ' + br(v)
def sinal(v): return ('-' if v < 0 else '+') + 'R$ ' + br(abs(v)) + ' contra a casa'
def pct(v, nd=0): return br(100 * v, nd) + '%'
def nota(t, cls='nota'): st.markdown(f'<div class="{cls}">{t}</div>', unsafe_allow_html=True)
def ddmm(d): return f'{d.day:02d}/{d.month:02d}'


@st.cache_resource(show_spinner='Lendo a planilha e conferindo os dados...')
def carregar(conteudo: bytes, _h: str):
    return motor.Base(io.BytesIO(conteudo))


# ---------------- barra lateral
with st.sidebar:
    st.markdown('## Fornada')
    st.caption('Previsão e decisão para padarias e complexos gastronômicos')
    arq = st.file_uploader('Planilha da casa (.xlsx)', type=['xlsx'])
    usar_demo = st.checkbox('Usar a base de demonstração', value=arq is None)
    hoje = st.date_input('Hoje', value=dt.date(2026, 11, 13), format='DD/MM/YYYY')
    st.caption('O aplicativo usa os dados até ontem.')

if arq is not None and not usar_demo:
    conteudo = arq.getvalue()
elif usar_demo:
    conteudo = open(DEMO, 'rb').read()
else:
    st.title('Fornada')
    st.info('Envie a planilha da casa na barra lateral, ou marque a base de demonstração.')
    st.stop()

B = carregar(conteudo, hashlib.md5(conteudo).hexdigest())
ontem = hoje - dt.timedelta(1)
amanha = hoje + dt.timedelta(1)
seg = hoje + dt.timedelta((7 - hoje.weekday()) % 7 or 7)
semana = [seg + dt.timedelta(k) for k in range(7)]

st.title('Fornada')
st.markdown(f'**{motor.NOME_DIA[hoje.weekday()].capitalize()}, {hoje:%d/%m/%Y}** · dados até {ontem:%d/%m} · '
            f'véspera de {motor.NOME_DIA[amanha.weekday()]} {ddmm(amanha)} · plano da semana de {ddmm(semana[0])} a {ddmm(semana[-1])}')

abas = st.tabs(['1. Dados', '2. Diagnóstico', '3. Confiabilidade', '4. Véspera', '5. Plano da semana',
                '6. Simulação', '7. Escala', '8. Ganho total'])

# ---------------- 1. dados
with abas[0]:
    c = B.conferencia(ontem)
    st.subheader('Conferência dos dados enviados')
    k = st.columns(4)
    k[0].metric('Período', f'{c["inicio"]:%m/%y} a {c["fim"]:%m/%y}')
    k[1].metric('Dias de histórico', br(c['dias']))
    k[2].metric('Itens no cadastro', c['n_itens'])
    k[3].metric('Itens planejados', c['n_planejados'])
    st.markdown('**O que o aplicativo encontrou**')
    linhas = []
    if c['sem_fechamento']:
        linhas.append(f'{len(c["sem_fechamento"])} dias sem fechamento nas últimas 4 semanas '
                      f'({", ".join(ddmm(d) for d in c["sem_fechamento"])}): ficam fora da conta da sobra.')
    for it, s in c['novos'].items():
        linhas.append(f'{it}: só {s} semanas de histórico. A recomendação é provisória.')
    if B.FORA:
        linhas.append('Fora do plano por enquanto (sazonais ou recém-lançados): ' + ', '.join(B.FORA) + '.')
    for l in linhas: st.markdown('- ' + l)
    if c['sem_custo']:
        nota(f'Faltam os custos de {len(c["sem_custo"])} itens. Digite o custo unitário da ficha técnica: '
             'é o único número que o gerente digita.', 'alerta')
        cols = st.columns(len(c['sem_custo']))
        for col, it in zip(cols, c['sem_custo']):
            col.number_input(it, min_value=0.0, step=0.1, format='%.2f', key='custo_' + it)
    custos = {it: st.session_state.get('custo_' + it, 0.0) for it in c['sem_custo']}
    faltando = [it for it, v in custos.items() if not v]
    if faltando:
        st.warning('Preencha os custos acima para liberar o plano e a simulação.')
        st.stop()
    B.set_custos(custos)
    st.success('Dados conferidos. Os cálculos das outras abas já usam estes custos.')

# ---------------- 2. diagnóstico
with abas[1]:
    a = ontem - dt.timedelta(6)
    D = B.diagnostico(a, ontem)
    st.subheader(f'O que aconteceu na semana de {ddmm(a)} a {ddmm(ontem)}')
    k = st.columns(4)
    k[0].metric('Perda com sobra, ao custo', rs(D['perda']))
    k[1].metric('Venda perdida, quando acabou', rs(D['venda_perdida']))
    k[2].metric('Descarte e quebra', rs(D['descarte'] + D['quebra']))
    k[3].metric('Revenda vencida', rs(D['vencimento']))
    nota(f'A venda perdida é estimada pela hora em que o item acabou: a venda do dia é dividida pela parte do movimento '
         f'que já tinha passado. Dias com fechamento: {D["dias_registrados"]} de 7.')
    g = D['itens'].reset_index()
    tab = pd.DataFrame({'Item': g['item'], 'Produzido': g.produzido.map(br), 'Sobra': g.sobra.map(br),
                        'Sobra (% da produção)': g.sobra_pct.map(pct), 'Perda (R$)': g.perda.map(br),
                        'Dias em que acabou': g.dias_acabou.astype(int), 'Venda perdida (R$)': g.venda_perdida.map(br)})
    st.dataframe(tab, hide_index=True, width='stretch', height=36 * (len(tab) + 1) + 24)
    st.markdown('**Perda com sobra por dia (R$)**')
    import altair as alt
    pdia = D['por_dia'].fillna(0)
    dfc = pd.DataFrame({'dia': [f'{motor.DIAS[d.weekday()]} {ddmm(d)}' for d in pdia.index], 'perda': pdia.values})
    st.altair_chart(alt.Chart(dfc).mark_bar(color='#C0392B').encode(
        x=alt.X('dia:N', sort=None, title=None, axis=alt.Axis(labelAngle=0, labelFontSize=14)),
        y=alt.Y('perda:Q', title='R$', axis=alt.Axis(format=',.0f'))).properties(height=260), width='stretch')

# ---------------- 3. confiabilidade
with abas[2]:
    st.subheader('Podemos confiar na previsão?')
    nota('Para cada um dos últimos 56 dias, o aplicativo previu a demanda só com o que sabia antes daquele dia '
         '(média dos 8 dias iguais da semana) e comparou com a demanda estimada. O erro médio é a média dessas diferenças.')
    cf = B.confiabilidade(ontem); novos = B.conferencia(ontem)['novos']
    def selo(e, it):
        e = round(e, 2)
        if it in novos: return 'provisória', 'histórico curto: conferir'
        if e <= 0.15: return 'alta', 'seguir a recomendação'
        if e <= 0.30: return 'média', 'seguir e conferir a sobra'
        return 'baixa', 'usar como limite, não como meta'
    tab = pd.DataFrame([dict(Item=it, **{'Erro médio': pct(e), 'Confiança': selo(e, it)[0], 'O que fazer': selo(e, it)[1]})
                        for it, e in cf.items()])
    st.dataframe(tab, hide_index=True, width='stretch', height=36 * (len(tab) + 1) + 24)

# ---------------- 4. véspera
def baixar(df_por_setor, nome):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as w:
        for s, df in df_por_setor.items(): df.to_excel(w, sheet_name=s[:31], index=False)
    return buf.getvalue()

with abas[3]:
    st.subheader(f'Véspera: decisões para {motor.NOME_DIA[amanha.weekday()]} {ddmm(amanha)}')
    ferv = {amanha} if amanha in FERIADOS else set()
    nota('Para cada item, o que a casa costuma fazer nesse dia da semana (mediana das 4 últimas semanas), '
         'o que o aplicativo recomenda e por quê. Na coluna "ajuste (%)" o gerente lança o que só ele sabe '
         '(chuva, evento no bairro); na coluna "encomenda", o que já está vendido e é produzido à parte.')
    pv = B.plano(amanha, ontem, ferv)
    ed = pd.DataFrame({'item': pv.item, 'prazo': pv.prazo, 'costuma fazer': pv.habitual.round().astype('Int64'),
                       'recomendado': pv.previsto, 'por quê': pv.motivo, 'ajuste (%)': 0, 'encomenda': 0})
    for it, q in B.E[B.E.data == amanha].groupby('item').quantidade.sum().items():
        ed.loc[ed.item == it, 'encomenda'] = int(q)
    ed = st.data_editor(ed, hide_index=True, width='stretch', height=36 * (len(ed) + 1) + 24, key='ed_vespera',
                        disabled=['item', 'prazo', 'costuma fazer', 'recomendado', 'por quê'],
                        column_config={'ajuste (%)': st.column_config.NumberColumn(min_value=-50, max_value=50, step=5),
                                       'encomenda': st.column_config.NumberColumn(min_value=0, step=1)})
    pv = B.plano(amanha, ontem, ferv, ajustes=dict(zip(ed.item, ed['ajuste (%)'])), encomendas=dict(zip(ed.item, ed.encomenda)))
    st.markdown('**Ordens de produção por setor**')
    setores = {s: g[['item', 'prazo', 'produzir']].rename(columns={'produzir': 'quantidade'}) for s, g in pv.groupby('setor', sort=False)}
    itens_set = list(setores.items())
    cols = [c for _ in range((len(itens_set) + 1) // 2) for c in st.columns(2)]
    for col, (s, g) in zip(cols, itens_set):
        col.markdown(f'**{s.capitalize()}**')
        col.dataframe(g[['item', 'prazo', 'quantidade']], hide_index=True, width='stretch')
    if 'Pão francês' in list(pv.item):
        q = int(pv[pv.item == 'Pão francês'].produzir.iloc[0]); f = B.fornadas(q)
        st.markdown(f'**Pão francês: {br(q)} pães em {len(f)} fornadas, pelos dois picos de venda**')
        st.dataframe(f.set_index('fornada').T.astype(str), width='stretch')
    st.download_button('Baixar as ordens de produção (Excel)', baixar(setores, 'ordens'),
                       file_name=f'ordens_{amanha:%Y-%m-%d}.xlsx', type='primary')

# ---------------- 5. plano da semana
with abas[4]:
    st.subheader(f'Plano preliminar da semana de {ddmm(semana[0])} a {ddmm(semana[-1])}')
    ferw = st.multiselect('Feriados da semana (tratados como domingo)', semana, format_func=lambda d: f'{motor.DIAS[d.weekday()]} {ddmm(d)}',
                          default=[d for d in semana if d in FERIADOS])
    tend = st.toggle('Previsão completa: acompanhar a tendência das duas últimas semanas', value=False)
    nota('O gerente lança o que já sabe com antecedência: um ajuste por item (por exemplo, a sopa cai quando esquenta) '
         'e as encomendas fechadas, produzidas à parte. No domingo à noite, com a semana fechada, o plano é refeito.')
    rots = [f'{motor.DIAS[d.weekday()]} {ddmm(d)}' for d in semana]
    base_ed = pd.DataFrame({'item': B.ITENS, 'ajuste (%)': 0, **{r: 0 for r in rots}})
    if st.query_params.get('exemplo') == '1' and usar_demo:   # correções da semana de demonstração
        base_ed.loc[base_ed.item == 'Sopa (porção)', 'ajuste (%)'] = -20
        base_ed.loc[base_ed.item == 'Bolo de cenoura (inteiro)', rots[3]] = 3
    st.markdown('**Ajuste por item (%) e encomendas já fechadas, por dia (unidades)**')
    aj = st.data_editor(base_ed, hide_index=True, key='ed_semana', disabled=['item'], width='stretch',
                        height=36 * (len(B.ITENS) + 1) + 24,
                        column_config={'ajuste (%)': st.column_config.NumberColumn(min_value=-50, max_value=50, step=5),
                                       **{r: st.column_config.NumberColumn(min_value=0, step=1) for r in rots}})
    ajd = dict(zip(aj.item, aj['ajuste (%)']))
    grade = {}
    for d, rot in zip(semana, rots):
        e = dict(zip(aj.item, aj[rot].astype(int)))
        p = B.plano(d, ontem, set(ferw), tend, ajd, e)
        grade[rot + (' feriado' if d in ferw else '')] = p.set_index('item').produzir
    G = pd.DataFrame(grade)
    st.markdown('**Quantidade a produzir por dia (já com ajustes e encomendas)**')
    st.dataframe(G, width='stretch', height=36 * (len(G) + 1) + 24)
    st.download_button('Baixar o plano da semana (Excel)', baixar({'plano': G.reset_index()}, 'plano'),
                       file_name=f'plano_{semana[0]:%Y-%m-%d}.xlsx')

# ---------------- 6. simulação
with abas[5]:
    st.subheader('Simulação: e se o aplicativo tivesse decidido?')
    if B.G is None:
        st.info('A simulação usa a aba "Gabarito", com a demanda verdadeira, que só existe na base de demonstração. '
                'Numa casa real, ela é feita no piloto, comparando semana a semana.')
    else:
        c1, c2, c3 = st.columns(3)
        T1 = c2.date_input('Até', value=min(dt.date(2026, 11, 15), B.ultimo), format='DD/MM/YYYY')
        T0 = c1.date_input('De', value=T1 - dt.timedelta(83), format='DD/MM/YYYY')
        tsim = c3.toggle('Previsão completa', value=True, help='Tira as encomendas do histórico e acompanha a tendência recente.')
        S = B.simular(T0, T1, tsim)
        t = S['tot']; ganho = t.margem['aplicativo'] - t.margem['casa']; n = S['dias']
        st.session_state['ganho_producao_ano'] = ganho * 365 / n
        k = st.columns(4)
        k[0].metric(f'Ganho de margem em {n} dias', rs(ganho))
        k[1].metric('Por ano', rs(ganho * 365 / n))
        k[2].metric('Venda perdida', rs(t.venda_perdida['aplicativo']), delta=sinal(t.venda_perdida['aplicativo'] - t.venda_perdida['casa']), delta_color='inverse')
        k[3].metric('Perda com sobra', rs(t.perda['aplicativo']), delta=sinal(t.perda['aplicativo'] - t.perda['casa']), delta_color='inverse')
        nota(f'Cada dia é decidido só com o que se sabia na véspera, e o resultado é medido contra a demanda verdadeira do gabarito. '
             f'O ganho por ano equivale a {pct(ganho * 365 / n / S["faturamento"], 1)} do faturamento anual dos {len(S["itens"])} itens simulados. '
             'Vem de faltar menos, não de sobrar menos: é a troca que a razão crítica manda fazer.')
        o = S['itens'].reset_index()
        tab = pd.DataFrame({'Item': o['item'], 'Ganho de margem (R$)': o.ganho.map(lambda v: ('+' if v > 0 else '') + br(v)),
                            'Sobra, casa': o.sobra_casa.map(pct), 'Sobra, aplicativo': o.sobra_app.map(pct),
                            f'Dias em que acabou, casa (de {n})': o.acabou_casa.astype(int),
                            'Dias em que acabou, aplicativo': o.acabou_app.astype(int)})
        st.dataframe(tab, hide_index=True, width='stretch', height=36 * (len(tab) + 1) + 24)
        st.markdown('**Pré-preparo de pratos sob pedido**')
        nota('Premissas editáveis: custo do pré-preparo por prato, parte da sobra reaproveitada, parte da falta que vira venda perdida '
             'e a folga que a casa usa hoje sobre a média.')
        prem = st.data_editor(pd.DataFrame([
            dict(item='Prato à la carte', preco=82.0, custo=26.0, custo_preparo=15.6, recuperada=0.5, falta_perdida=0.3, folga=1.25),
            dict(item='Pizza', preco=85.0, custo=24.0, custo_preparo=4.0, recuperada=0.0, falta_perdida=0.5, folga=1.25)]),
            hide_index=True, key='ed_prem', disabled=['item'], width='stretch')
        PP = B.simular_preparo(T0, T1, prem.to_dict('records'))
        PP['decisão'] = np.where(PP.ganho_ano > 0, 'usar o aplicativo', 'manter a regra da casa')
        st.session_state['ganho_preparo_ano'] = PP[PP.ganho_ano > 0].ganho_ano.sum()
        st.dataframe(pd.DataFrame({'Item': PP['item'], 'Razão crítica': PP.razao_critica.map(pct),
                                   'Ganho no período (R$)': PP.ganho_periodo.map(br), 'Por ano (R$)': PP.ganho_ano.map(br),
                                   'Decisão': PP['decisão']}), hide_index=True, width='stretch')

# ---------------- 7. escala
with abas[6]:
    st.subheader('Escala por setor, com folgas 5x2 (programação inteira)')
    nota('Mínimo de pessoas por dia na casa toda; o aplicativo reparte o mínimo entre os setores pelo movimento de cada um '
         'e calcula, setor por setor, quantas pessoas começam a semana em cada dia de folga.')
    ordem = [1, 2, 3, 4, 5, 6, 0]  # seg..dom no índice dom=0
    nomes = ['seg', 'ter', 'qua', 'qui', 'sex', 'sáb', 'dom']
    padrao = [105, 80, 80, 85, 95, 110, 125]
    cols = st.columns(7)
    MINv = [0] * 7
    for col, j, nm in zip(cols, ordem, nomes):
        MINv[j] = col.number_input(nm, min_value=0, value=padrao[j], step=1, key='min_' + nm)
    c1, c2 = st.columns(2)
    parte = c1.slider('Parte da falta de hoje paga em hora extra', 0, 100, 50, 10, format='%d%%') / 100
    sal = c2.number_input('Salário médio de funcionário (R$)', value=float(round(B.EQ[B.EQ.funcao == "funcionário"].salario_mensal.mean())), step=50.0)
    E = B.escala(MINv, ontem - dt.timedelta(81), sal, parte)
    st.session_state['escala'] = E
    k = st.columns(4)
    k[0].metric('Escalados hoje', E['atual']); k[1].metric('Necessários (ótimo)', E['otimo'])
    k[2].metric('Falta por semana', f'{E["falta"]} pessoas-dia', help=f'{E["falta"] * 8} horas')
    k[3].metric('Sobra por semana', f'{E["sobra"]} pessoas-dia')
    rows = []
    for r in E['R'].itertuples():
        for nm, j in zip(nomes, ordem):
            rows.append(dict(setor=r.setor, dia=nm, hoje=int(r.atual_dia[j]), minimo=int(r.minimo[j]), otimo=int(r.otimo_dia[j])))
    X = pd.DataFrame(rows)
    piv = X.pivot(index='setor', columns='dia', values='hoje')[nomes]
    mn = X.pivot(index='setor', columns='dia', values='minimo')[nomes]
    txt = piv.astype(str) + ' / ' + mn.astype(str)
    def cor(_):
        return pd.DataFrame(np.where(piv < mn, 'background-color:#F6C4C0;color:#7A0000;font-weight:700',
                                     np.where(piv > mn, 'background-color:#CFE0F7;color:#0B1F5C', '')), index=piv.index, columns=piv.columns)
    st.markdown('**Hoje / mínimo, por setor e dia** (vermelho: falta gente; azul: sobra)')
    st.dataframe(txt.style.apply(cor, axis=None), width='stretch', height=36 * (len(txt) + 1) + 24)
    ot = E['R'].set_index('setor')[['atual', 'otimo']].rename(columns={'atual': 'pessoas hoje', 'otimo': 'pessoas na escala ótima'})
    st.markdown('**Pessoas por setor**')
    st.dataframe(ot, width='stretch', height=36 * (len(ot) + 1) + 24)
    nota(f'A escala ótima cobre todos os mínimos só mudando as folgas. Por setor, a casa precisa de {E["otimo"]} pessoas e tem {E["atual"]}: '
         f'{E["postos"]} posto a menos, {rs(E["posto_ano"] * E["postos"])} por ano. A falta de hoje soma {E["falta"] * 8} horas por semana; '
         f'com {pct(parte)} dela paga em hora extra (adicional de 50%, 100% no domingo, e encargos), a escala ótima economiza cerca de '
         f'{rs(E["hora_extra_ano"])} por ano.')

# ---------------- 8. ganho total
with abas[7]:
    st.subheader('O ganho total estimado da unidade, por ano')
    gp = st.session_state.get('ganho_producao_ano'); gpp = st.session_state.get('ganho_preparo_ano'); E = st.session_state.get('escala')
    if gp is None or E is None:
        st.info('Abra as abas 6 e 7 para calcular.')
    else:
        fat = B.V[B.V.data > B.ultimo - dt.timedelta(365)].faturamento.sum()
        linhas = [('Produção diária', gp, 'simulação contra o gabarito'),
                  ('Pré-preparo de pratos sob pedido', gpp, 'simulação com premissas; onde a regra da casa é melhor, ela é mantida'),
                  ('Escala: postos', E['posto_ano'] * E['postos'], f'{E["postos"]} posto, salário médio com 13º, férias e encargos'),
                  ('Escala: hora extra', E['hora_extra_ano'], 'parte da falta de hoje paga em hora extra')]
        tot = sum(v for _, v, _ in linhas); sem_he = tot - E['hora_extra_ano']
        k = st.columns(3)
        k[0].metric('Ganho por ano', rs(tot)); k[1].metric('Sobre o faturamento', pct(tot / fat, 1))
        k[2].metric('Sem a hora extra', rs(sem_he), help=pct(sem_he / fat, 1) + ' do faturamento')
        st.dataframe(pd.DataFrame([dict(**{'De onde vem': a, 'Por ano (R$)': br(v), 'Como foi calculado': c}) for a, v, c in linhas]),
                     hide_index=True, width='stretch')
        nota(f'Faturamento dos últimos 12 meses: {rs(fat)}. O ganho é lucro: aluguel, energia e o restante da folha não mudam. '
             'Ficaram fora da conta as correções do gerente, o empório e os frios.')
