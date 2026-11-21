"""Fornada: motor de cálculo.
Previsão (demanda corrigida pela hora em que o item acabou), razão crítica,
confiabilidade, plano de produção, simulação contra o gabarito e escala por setor.
Tudo a partir da planilha da casa (o mesmo modelo da base fictícia)."""
import json, os, datetime as dt
import numpy as np, pandas as pd
from scipy.stats import norm

AQUI = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(AQUI, 'perfis.json'), encoding='utf-8'))
H, PROF, MAP = CFG['H'], CFG['PROF'], CFG['MAP']
DIAS = ['seg', 'ter', 'qua', 'qui', 'sex', 'sáb', 'dom']
NOME_DIA = ['segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado', 'domingo']
FORNADAS = [('5h30', 6, 8, 'produção'), ('7h30', 8, 10, 'produção'), ('10h', 10, 13, 'produção'),
            ('13h', 13, 16, 'tarde'), ('15h30', 16, 18, 'tarde'), ('17h30', 18, 20, 'tarde'), ('19h30', 20, 22, 'tarde')]


def _d(s):
    return pd.to_datetime(s).dt.date


class Base:
    """Lê a planilha e guarda o histórico já corrigido."""

    def __init__(self, arquivo):
        x = pd.ExcelFile(arquivo)
        self.abas = x.sheet_names
        le = lambda a: pd.read_excel(x, a) if a in x.sheet_names else None
        self.itens = le('Itens')
        self.P = le('Producao_sobra'); self.P['data'] = _d(self.P.data)
        self.V = le('Vendas_diarias'); self.V['data'] = _d(self.V.data)
        self.E = le('Encomendas')
        if self.E is None: self.E = pd.DataFrame(columns=['data', 'item', 'quantidade', 'retirada'])
        self.E['data'] = _d(self.E.data)
        self.cal = le('Calendario'); self.cal['data'] = _d(self.cal.data)
        self.PR = le('Perdas_revenda')
        if self.PR is not None: self.PR['data'] = _d(self.PR.data)
        self.M = le('Movimento_hora')
        if self.M is not None: self.M['data'] = _d(self.M.data)
        self.EQ = le('Equipe')
        g = le('Gabarito')
        self.G = None
        if g is not None:
            g = g[['data', 'item', 'demanda_verdadeira']].dropna(subset=['data'])
            g['data'] = _d(g.data); self.G = g
        self.P['hora_acabou'] = self.P.hora_acabou.apply(self._hora)
        self.FER = set(self.cal[self.cal.feriado.notna() & (self.cal.feriado.astype(str).str.strip() != '')].data)
        self.custo = dict(zip(self.itens.item, self.itens.custo_atual))
        self._prep()

    @staticmethod
    def _hora(h):
        if isinstance(h, str) and ':' in h: return h[:5]
        if isinstance(h, dt.time): return h.strftime('%H:%M')
        return ''

    def _prep(self):
        it = self.itens.set_index('item')
        self.info = it
        planej = it[it.tipo.isin([1, 3])].index
        ult = self.P.data.max()
        rec = self.P[(self.P.data > ult - dt.timedelta(56)) & self.P.vendido.notna()].groupby('item').data.nunique()
        self.ITENS = [i for i in planej if rec.get(i, 0) >= 42]   # vendido em 3/4 dos últimos 56 dias
        self.FORA = [i for i in planej if 0 < rec.get(i, 0) < 42]  # sazonais ou recém-lançados
        self.ultimo = ult
        self.EST = {}
        enc = self.E.groupby(['data', 'item']).quantidade.sum().to_dict()
        for r in self.P[self.P.item.isin(self.ITENS)].itertuples():
            if pd.isna(r.vendido): continue
            v = r.vendido - enc.get((r.data, r.item), 0)
            pf = MAP.get(it.loc[r.item, 'perfil_de_venda'], 'dia')
            ac = r.hora_acabou != ''
            self.EST[(r.data, r.item)] = (v / self.cum(pf, r.hora_acabou) if ac else v, v, ac)

    @staticmethod
    def cum(pf, hhmm):
        t = int(hhmm[:2]) + int(hhmm[3:]) / 60; c = 0
        for i, h in enumerate(H): c += PROF[pf][i] * min(1, max(0, t - h))
        return max(c, 0.05)

    def set_custos(self, novos):
        for k, v in novos.items():
            self.itens.loc[self.itens.item == k, 'custo_atual'] = v
        self.info = self.itens.set_index('item')

    # ---------- características do item
    def pr(self, it): return float(self.info.loc[it, 'preco_atual'])
    def cu(self, it): return float(self.info.loc[it, 'custo_atual'])
    def rr(self, it):
        r = self.info.loc[it, 'parcela_recuperada']; return 0.0 if pd.isna(r) else float(r)

    def rc(self, it):
        pr, cu, r = self.pr(it), self.cu(it), self.rr(it)
        x = (pr - cu) / ((pr - cu) + cu * (1 - r))
        if str(self.info.loc[it, 'obrigatorio']).strip().lower() == 'sim': x = max(x, 0.9)
        return x

    def dia_sem(self, d, ferw=()):
        return 6 if (d in self.FER or d in ferw) else d.weekday()

    # ---------- 1. conferência dos dados
    def conferencia(self, ate):
        a = ate - dt.timedelta(27)
        x = self.P[(self.P.data >= a) & (self.P.data <= ate) & self.P.item.isin(self.ITENS)]
        sem = sorted(x[x.produzido.isna()].data.unique())
        sem_custo = [i for i in self.itens.item if pd.isna(self.custo.get(i))]
        semanas = {it: (ate - self.P[(self.P.item == it) & self.P.produzido.notna()].data.min()).days // 7 for it in self.ITENS}
        novos = {k: v for k, v in semanas.items() if v < 26}
        return dict(inicio=self.P.data.min(), fim=self.P.data.max(), dias=self.P.data.nunique(),
                    sem_fechamento=sem, sem_custo=sem_custo, novos=novos, n_itens=len(self.itens),
                    n_planejados=len(self.ITENS), linhas_vendas=len(self.V))

    # ---------- 2. diagnóstico
    def diagnostico(self, a, b):
        w = self.P[(self.P.data >= a) & (self.P.data <= b) & self.P.item.isin(self.ITENS)].dropna(subset=['produzido']).copy()
        w['c'] = w.item.map(self.cu)
        desc = (w.descartado * w.c).sum(); queb = (w.quebrado * w.c).sum()
        venc = self.PR[(self.PR.data >= a) & (self.PR.data <= b)].perda_ao_custo.sum() if self.PR is not None else 0
        w['perda'] = (w.descartado + w.quebrado) * w.c
        g = w.groupby('item').agg(produzido=('produzido', 'sum'), sobra=('sobra', 'sum'), perda=('perda', 'sum'))
        g['sobra_pct'] = g.sobra / g.produzido
        fi, ac = {}, {}
        for (d, it), (e, v, acb) in self.EST.items():
            if a <= d <= b and acb:
                fi[it] = fi.get(it, 0) + (e - v) * self.pr(it); ac[it] = ac.get(it, 0) + 1
        g['venda_perdida'] = pd.Series(fi); g['dias_acabou'] = pd.Series(ac)
        g = g.fillna(0)
        pdia = w.groupby('data').perda.sum()
        dias = [a + dt.timedelta(k) for k in range((b - a).days + 1)]
        pdia = pdia.reindex(dias)
        return dict(descarte=desc, quebra=queb, vencimento=venc, perda=desc + queb + venc,
                    venda_perdida=sum(fi.values()), itens=g.sort_values('perda', ascending=False),
                    por_dia=pdia, dias_registrados=w.data.nunique())

    # ---------- 3. confiabilidade
    def confiabilidade(self, b, dias=56):
        out = {}
        for it in self.ITENS:
            errs = []
            for k in range(dias):
                d = b - dt.timedelta(k)
                if (d, it) not in self.EST: continue
                hist = [self.EST.get((d - dt.timedelta(7 * j), it)) for j in range(1, 9)]
                hist = [h[0] for h in hist if h]
                if len(hist) < 4: continue
                f = np.mean(hist); real = self.EST[(d, it)][0]
                errs.append(abs(f - real) / max(real, 1))
            out[it] = np.mean(errs) if errs else np.nan
        s = pd.Series(out).sort_values()
        return s

    # ---------- 4. plano
    def previsao(self, it, d, b, ferw=(), tendencia=False):
        wd = self.dia_sem(d, ferw); hist = []
        for j in range(1, 90):
            dd = d - dt.timedelta(j)
            if dd > b: continue
            if self.dia_sem(dd) == wd and (dd, it) in self.EST: hist.append(self.EST[(dd, it)][0])
            if len(hist) == 8: break
        mu, sd = np.mean(hist), np.std(hist, ddof=1)
        f = 1.0
        if tendencia:
            rec = [self.EST[(b - dt.timedelta(k), it)][0] for k in range(14) if (b - dt.timedelta(k), it) in self.EST]
            allw = [self.EST[(b - dt.timedelta(k), it)][0] for k in range(56) if (b - dt.timedelta(k), it) in self.EST]
            if rec and allw and np.mean(allw) > 0: f = np.mean(rec) / np.mean(allw)
        rc = self.rc(it)
        return dict(q=int(round(f * (mu + norm.ppf(rc) * sd))), mu=mu * f, sd=sd * f, rc=rc, n=len(hist))

    def habitual(self, it, d, b, ferw=()):
        """O que a casa costuma fazer nesse dia da semana (mediana das 4 últimas semanas, sem encomendas)."""
        wd = self.dia_sem(d, ferw)
        enc = self.E[self.E.item == it].groupby('data').quantidade.sum().to_dict()
        x = self.P[(self.P.item == it) & (self.P.data <= b) & self.P.produzido.notna()]
        x = x[x.data.map(self.dia_sem) == wd].sort_values('data').tail(4)
        if x.empty: return np.nan, x
        return float(np.median([r.produzido - enc.get(r.data, 0) for r in x.itertuples()])), x

    def motivo(self, it, x, q, hab):
        if x.empty: return 'sem histórico neste dia da semana'
        n = len(x); ac = (x.hora_acabou != '').sum(); sob = x.sobra.mean()
        if q > hab * 1.05:
            return f'acabou em {ac} dos últimos {n}' + (f', às {x.hora_acabou[x.hora_acabou != ""].iloc[-1]}' if ac else '')
        if q < hab * 0.95:
            return f'sobra média de {sob:.0f} nos últimos {n}'
        return 'perto do habitual'

    def plano(self, d, b, ferw=(), tendencia=False, ajustes=None, encomendas=None):
        ajustes = ajustes or {}; encomendas = encomendas or {}
        rows = []
        for it in self.ITENS:
            p = self.previsao(it, d, b, ferw, tendencia)
            hab, x = self.habitual(it, d, b, ferw)
            aj = ajustes.get(it, 0)
            q = int(round(p['q'] * (1 + aj / 100)))
            rows.append(dict(item=it, setor=self.info.loc[it, 'setor'], prazo=self.info.loc[it, 'decidir_ate'],
                             habitual=hab, previsto=p['q'], ajuste_pct=aj, recomendado=q,
                             encomenda=encomendas.get(it, 0), produzir=q + encomendas.get(it, 0),
                             razao_critica=p['rc'], media=p['mu'], desvio=p['sd'],
                             motivo=self.motivo(it, x, p['q'], hab)))
        return pd.DataFrame(rows)

    @staticmethod
    def fornadas(q):
        pf = PROF['pao']; fr = []
        for nome, h0, h1, turno in FORNADAS:
            fr.append(sum(pf[i] for i, h in enumerate(H) if h0 <= h < h1))
        fr = np.array(fr) / sum(fr); qs = np.floor(q * fr).astype(int)
        for j in np.argsort(-(q * fr - qs))[:q - qs.sum()]: qs[j] += 1
        return pd.DataFrame({'fornada': [f[0] for f in FORNADAS], 'pães': qs, 'turno': [f[3] for f in FORNADAS]})

    # ---------- 5. simulação contra o gabarito
    def simular(self, T0, T1, tendencia=True, regra_obrig=True):
        DV = {(r.data, r.item): r.demanda_verdadeira for r in self.G.itertuples()}
        enc = self.E.groupby(['data', 'item']).quantidade.sum().to_dict()
        sim_itens = [it for it in self.ITENS
                     if self.P[(self.P.item == it) & self.P.produzido.notna()].data.min() <= T0 - dt.timedelta(56)]
        res = []
        for it in sim_itens:
            pr, cu, r = self.pr(it), self.cu(it), self.rr(it)
            rc = (pr - cu) / ((pr - cu) + cu * (1 - r))
            if regra_obrig and str(self.info.loc[it, 'obrigatorio']).strip().lower() == 'sim': rc = max(rc, 0.9)
            z = norm.ppf(rc)
            x = self.P[self.P.item == it].set_index('data')
            d = T0
            while d <= T1:
                if d not in x.index or pd.isna(x.loc[d, 'produzido']): d += dt.timedelta(1); continue
                hist = [self.EST.get((d - dt.timedelta(7 * k), it)) for k in range(1, 9)]
                hist = [h[0] for h in hist if h is not None]
                mu, sd = np.mean(hist), np.std(hist, ddof=1)
                if tendencia:
                    rec = [self.EST[(d - dt.timedelta(k), it)][0] for k in range(1, 15) if (d - dt.timedelta(k), it) in self.EST]
                    allw = [self.EST[(d - dt.timedelta(k), it)][0] for k in range(1, 57) if (d - dt.timedelta(k), it) in self.EST]
                    if rec and allw and np.mean(allw) > 0:
                        f = np.mean(rec) / np.mean(allw); mu *= f; sd *= f
                q = int(round(mu + z * sd))
                dem = DV.get((d, it), 0)
                atual = x.loc[d, 'produzido'] - enc.get((d, it), 0)
                for cen, qq in (('casa', atual), ('aplicativo', q)):
                    v = min(dem, qq); s = qq - v
                    res.append(dict(item=it, data=d, cenario=cen, produzido=qq, vendido=v, sobra=s, falta=dem - v,
                                    acabou=dem > qq, margem=v * pr - qq * cu + s * cu * r,
                                    perda=s * cu * (1 - r), venda_perdida=(dem - v) * pr))
                d += dt.timedelta(1)
        R = pd.DataFrame(res)
        g = R.groupby(['item', 'cenario']).agg(produzido=('produzido', 'sum'), sobra=('sobra', 'sum'),
                                               acabou=('acabou', 'sum'), margem=('margem', 'sum')).unstack('cenario')
        out = pd.DataFrame({'ganho': g['margem']['aplicativo'] - g['margem']['casa'],
                            'sobra_casa': g['sobra']['casa'] / g['produzido']['casa'],
                            'sobra_app': g['sobra']['aplicativo'] / g['produzido']['aplicativo'],
                            'acabou_casa': g['acabou']['casa'], 'acabou_app': g['acabou']['aplicativo']}).sort_values('ganho', ascending=False)
        tot = R.groupby('cenario')[['margem', 'perda', 'venda_perdida']].sum()
        fat = self.V[(self.V.data > self.ultimo - dt.timedelta(365)) & self.V.item.isin(sim_itens)].faturamento.sum()  # 12 meses
        return dict(R=R, itens=out, tot=tot, dias=R.data.nunique(), faturamento=fat)

    def simular_preparo(self, T0, T1, premissas):
        """premissas: lista de dict(item, preco, custo, custo_preparo, recuperada, falta_perdida, folga)."""
        out = []
        for p in premissas:
            dem = {r.data: r.demanda_verdadeira for r in self.G[self.G.item == p['item']].itertuples()}
            ganho = p['falta_perdida'] * (p['preco'] - p['custo']); perda = p['custo_preparo'] * (1 - p['recuperada'])
            rc = ganho / (ganho + perda); z = norm.ppf(rc)
            tot = {'casa': [0, 0], 'app': [0, 0]}; fix = {}; d = T0
            while d <= T1:
                wd = self.dia_sem(d)
                hist = [h for h in (dem.get(d - dt.timedelta(7 * k)) for k in range(1, 9)) if h is not None]
                key = ((d - T0).days // 28, wd)
                if key not in fix: fix[key] = round(p['folga'] * np.mean(hist))
                rec = [h for h in (dem.get(d - dt.timedelta(k)) for k in range(1, 15)) if h is not None]
                allw = [h for h in (dem.get(d - dt.timedelta(k)) for k in range(1, 57)) if h is not None]
                f = np.mean(rec) / np.mean(allw)
                qa = round(f * (np.mean(hist) + z * np.std(hist, ddof=1)))
                x = dem[d]
                for k, q in (('casa', fix[key]), ('app', qa)):
                    tot[k][0] += max(q - x, 0) * perda; tot[k][1] += max(x - q, 0) * ganho
                d += dt.timedelta(1)
            n = (T1 - T0).days + 1
            ca, cb = sum(tot['casa']), sum(tot['app'])
            out.append(dict(item=p['item'], razao_critica=rc, custo_casa=ca, custo_app=cb,
                            ganho_periodo=ca - cb, ganho_ano=(ca - cb) * 365 / n))
        return pd.DataFrame(out)

    # ---------- 6. escala por setor (programação inteira)
    def escala(self, minimos, desde, salario=None, parte_he=0.5, fator_enc=1.4):
        from scipy.optimize import milp, LinearConstraint, Bounds
        OFF = {'G1': (0, 1), 'G2': (1, 2), 'G3': (2, 3), 'G4': (3, 4), 'G5': (4, 5), 'G6': (5, 6), 'G7': (6, 0)}  # 0=dom
        MIN = np.array(minimos)  # dom..sáb
        EQ = self.EQ; esc = EQ[EQ.grupo_de_folga != 'férias']
        SET = list(EQ.setor.unique())
        cur = {s: np.zeros(7, int) for s in SET}
        for r in esc.itertuples():
            for d in range(7):
                if d not in OFF[r.grupo_de_folga]: cur[r.setor][d] += 1
        V = self.V[self.V.data >= desde].copy(); V['dw'] = V.data.map(lambda d: (d.weekday() + 1) % 7)
        setor_item = dict(zip(self.itens.item, self.itens.setor))
        def prof(cats):
            x = V[V.item.map(setor_item).isin(cats)].groupby('dw').faturamento.sum(); return (x / x.sum()).reindex(range(7)).values
        M = self.M.copy(); M['dw'] = M.data.map(lambda d: (d.weekday() + 1) % 7)
        pc = M.groupby('dw').cupons.sum(); pc = (pc / pc.sum()).reindex(range(7)).values
        pad = prof(['panificação', 'confeitaria', 'salgados', 'balcão', 'balcão e frios'])
        rest = prof(['cozinha', 'pizzaria']); emp = prof(['empório'])
        PF = {'Produção da padaria': pad, 'Confeitaria': pad, 'Balcão da padaria e frios': pad,
              'Cozinha dos restaurantes': rest, 'Salão e garçons': rest, 'Empório': emp,
              'Caixa': pc, 'Limpeza e copa': pc}
        tot_cur = {s: cur[s].sum() for s in SET}
        need = {s: tot_cur[s] * MIN.sum() / sum(tot_cur.values()) for s in SET}
        X = np.array([[need[s] * PF.get(s, np.ones(7) / 7)[d] for d in range(7)] for s in SET])
        for _ in range(200):
            X *= (MIN / X.sum(0))[None, :]; X *= (np.array([need[s] for s in SET]) / X.sum(1))[:, None]
        Mi = np.floor(X).astype(int)
        for d in range(7):
            k = MIN[d] - Mi[:, d].sum(); order = np.argsort(-(X[:, d] - Mi[:, d]))
            for j in order[:k]: Mi[j, d] += 1
        A = np.array([[1 if (d - s) % 7 < 5 else 0 for s in range(7)] for d in range(7)])
        res = []
        for i, s in enumerate(SET):
            r = milp(np.ones(7), constraints=LinearConstraint(A, Mi[i], np.inf), integrality=np.ones(7), bounds=Bounds(0, np.inf))
            xs = np.round(r.x).astype(int)
            res.append(dict(setor=s, atual=int(len(esc[esc.setor == s])), otimo=int(xs.sum()), minimo=Mi[i],
                            atual_dia=cur[s], otimo_dia=A @ xs, comecam=xs))
        R = pd.DataFrame(res)
        F = sum(np.clip(r.minimo - r.atual_dia, 0, None) for r in R.itertuples())
        S = sum(np.clip(r.atual_dia - r.minimo, 0, None) for r in R.itertuples())
        if salario is None: salario = float(EQ[EQ.funcao == 'funcionário'].salario_mensal.mean())
        mult = np.array([2.0, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5])
        he = float((F * 8 * parte_he * salario / 220 * mult * fator_enc).sum() * 52)
        posto = salario * 13.33 * fator_enc
        return dict(R=R, falta_dia=F, sobra_dia=S, falta=int(F.sum()), sobra=int(S.sum()),
                    atual=int(R.atual.sum()), otimo=int(R.otimo.sum()), salario=salario,
                    hora_extra_ano=he, posto_ano=posto, postos=int(R.atual.sum() - R.otimo.sum()))
