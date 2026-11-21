# Fornada: aplicativo na internet (Streamlit)

O gerente usa o Fornada pelo navegador, no computador ou no celular. O cálculo roda no servidor; a casa não instala nada.

## Arquivos

- `app.py`: as telas (8 abas: Dados, Diagnóstico, Confiabilidade, Véspera, Plano da semana, Simulação, Escala, Ganho total).
- `motor.py`: o motor de cálculo (previsão, razão crítica, confiabilidade, plano, simulação, escala por programação inteira).
- `perfis.json`: a curva de venda por hora de cada perfil de item, usada para estimar a demanda quando o item acaba.
- `dados/Fornada_base_ficticia.xlsx`: a base de demonstração.
- `requirements.txt`, `.streamlit/config.toml`: dependências e tema.

## Rodar no próprio computador (para testar)

```
pip install -r requirements.txt
streamlit run app.py
```

Abre em http://localhost:8501. Com `?exemplo=1` no endereço, a aba 5 já vem com as correções da semana de demonstração (sopa −20% e 3 bolos de cenoura na quinta).

## Publicar na internet

Opção 1, Streamlit Community Cloud (gratuito, bom para demonstração):
1. Criar um repositório no GitHub com estes arquivos.
2. Entrar em share.streamlit.io com a conta do GitHub, escolher "Create app", o repositório e o arquivo `app.py`.
3. Em "Settings", "Sharing", deixar o aplicativo visível só para os e-mails autorizados.

Opção 2, servidor próprio (para clientes, com dados reais): uma máquina virtual pequena (2 vCPU, 4 GB) com o mesmo comando, atrás de um endereço com HTTPS e senha. Os dados da casa ficam só nesse servidor, o que facilita o contrato de confidencialidade e a LGPD.

## Dados da casa

A planilha segue o modelo da base: abas Itens, Calendario, Vendas_diarias, Producao_sobra, Encomendas, Perdas_revenda, Movimento_hora e Equipe. A aba Gabarito só existe na base de demonstração, e é ela que permite a simulação contra a demanda verdadeira.
