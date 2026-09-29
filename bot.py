import asyncio
import warnings
import sys
import ccxt.async_support as ccxt
import aiohttp

# Ignora avisos de depravação do async/ccxt
warnings.filterwarnings("ignore")

# ==============================================================================
# CONFIGURAÇÕES DO TELEGRAM
# ==============================================================================
TELEGRAM_BOT_TOKEN = '8629751246:AAFo0b0he6XEYePKSKJCI9cYvfB945J2VsI'
TELEGRAM_CHAT_ID = '8904318617'

# ==============================================================================
# CONFIGURAÇÕES DA OPERAÇÃO E MERCADO
# ==============================================================================
PARES = [
    'ETH/USDT',
    'BTC/USDT',
    'SOL/USDT',
    'BNB/USDT',
    'XRP/USDT',
    'PEPE/USDT',
    'SUI/USDT',
    'NEAR/USDT',
    'AVAX/USDT',
    'LINK/USDT',
    'APT/USDT',
    'RENDER/USDT'
]

CORRETORAS_ALVO = [
    'binance',
    'gateio',
    'kucoin',
    'okx',
    'bybit',
    'mexc',
    'bitget',
    'kraken',
    'bingx',
    'htx',
    'coinex',
    'bitmart',
    'coinbase',
    'bitfinex',
    'phemex'
]

VALOR_INVESTIDO_USD = 100.0   # Banca simulada por operação
INTERVALO_SEGUNDOS = 300       # Tempo seguro entre varreduras

# ==============================================================================
# PARÂMETROS DE FILTRAGEM
# ==============================================================================
SPREAD_MINIMO_PCT = 0.25      # Spread bruto mínimo
SPREAD_MAXIMO_PCT = 12.0      # Evita falhas de API / pares ilíquidos ilógicos
VOLUME_MINIMO_24H = 1000      # Volume mínimo em USD na corretora
TAXA_ESTIMADA_TOTAL_PCT = 0.15 # Taxa estimada combinada (compra + venda)


async def enviar_mensagem_telegram(texto):
    """Envia alertas formatados diretamente para o chat do Telegram."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": texto,
        "parse_mode": "Markdown"
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=5) as resp:
                if resp.status != 200:
                    print(f"\n⚠️ [Erro Telegram] Retorno HTTP Status: {resp.status}")
    except Exception as e:
        print(f"\n⚠️ [Erro Conexão Telegram]: {e}")


async def consultar_corretora_par(exchange_id, symbol, semaforo, contador_progresso):
    """Consulta o ticker de um par em uma determinada corretora e atualiza o progresso."""
    async with semaforo:
        exchange = None
        resultado = None
        sucesso = False
        try:
            exchange_class = getattr(ccxt, exchange_id)
            exchange = exchange_class({
                'enableRateLimit': True,
                'timeout': 3500
            })
            
            ticker = await exchange.fetch_ticker(symbol)

            bid = ticker.get('bid')
            ask = ticker.get('ask')
            vol = ticker.get('quoteVolume') or ticker.get('baseVolume') or 0

            if bid and ask and float(bid) > 0 and float(ask) > 0 and float(vol) >= VOLUME_MINIMO_24H:
                resultado = {
                    'exchange': exchange_id.upper(),
                    'symbol': symbol,
                    'bid': float(bid),
                    'ask': float(ask),
                    'volume': float(vol)
                }
                sucesso = True
        except Exception:
            sucesso = False
            resultado = None
        finally:
            if exchange is not None:
                try:
                    await exchange.close()
                except Exception:
                    pass

            # Atualiza barra de porcentagem e status
            contador_progresso['concluidos'] += 1
            porcentagem = (contador_progresso['concluidos'] / contador_progresso['total']) * 100
            bar_length = 20
            filled_length = int(bar_length * contador_progresso['concluidos'] // contador_progresso['total'])
            bar = '█' * filled_length + '-' * (bar_length - filled_length)
            
            sys.stdout.write(f"\r🔍 Varredura: [{bar}] {porcentagem:5.1f}% ({contador_progresso['concluidos']}/{contador_progresso['total']})")
            sys.stdout.flush()

        return exchange_id, sucesso, resultado


def estimar_tempo_operacao(spread_pct, moeda):
    """Estima a janela de tempo com base na volatilidade e spread."""
    if moeda in ['BTC', 'ETH', 'SOL']:
        if spread_pct < 0.5:
            return "⚡ Rápido (~1 a 3 min)"
        elif spread_pct < 1.5:
            return "⏱ Moderado (~3 a 6 min)"
        else:
            return "🐢 Amplo (~6 a 12 min)"
    else:
        if spread_pct < 0.8:
            return "⚡ Rápido (~2 a 5 min)"
        elif spread_pct < 2.0:
            return "⏱️ Moderado (~5 a 10 min)"
        else:
            return "🐢 Amplo (~10 a 18 min)"


async def executar_varredura():
    """Realiza a consulta com indicadores visuais no terminal."""
    total_corretoras = len(CORRETORAS_ALVO)
    print(f"\n⚡ Iniciando Varredura Spot em {total_corretoras} Corretoras...")

    semaforo = asyncio.Semaphore(8)
    total_tarefas = len(PARES) * len(CORRETORAS_ALVO)
    contador_progresso = {'concluidos': 0, 'total': total_tarefas}

    tarefas = []
    for par in PARES:
        for ex in CORRETORAS_ALVO:
            tarefas.append(consultar_corretora_par(ex, par, semaforo, contador_progresso))

    resultados = await asyncio.gather(*tarefas)
    print()  # Quebra de linha após a barra de 100%

    # Mapeamento de status de conexão das corretoras
    status_corretoras = {ex.upper(): False for ex in CORRETORAS_ALVO}
    dados_validos = []

    for ex_id, sucesso, dado in resultados:
        if sucesso and dado is not None:
            status_corretoras[ex_id.upper()] = True
            dados_validos.append(dado)

    # --- EXIBIÇÃO DE CONFIRMAÇÃO DE CONEXÃO (1/15, 2/15...) ---
    print("\n📡 Status de Conexão com as Corretoras:")
    corretoras_com_sucesso = [ex for ex, conectado in status_corretoras.items() if conectado]
    corretoras_com_falha = [ex for ex, conectado in status_corretoras.items() if not conectado]

    for idx, ex in enumerate(CORRETORAS_ALVO, 1):
        ex_nome = ex.upper()
        if status_corretoras[ex_nome]:
            print(f"  [{idx:2d}/{total_corretoras}] ✅ {ex_nome:<10} - Conectado com sucesso")
        else:
            print(f"  [{idx:2d}/{total_corretoras}] ❌ {ex_nome:<10} - Sem resposta / Falha de conexão")

    if corretoras_com_falha:
        print(f"\n⚠️ Corretoras que NÃO foi possível conectar nesta rodada ({len(corretoras_com_falha)}/{total_corretoras}):")
        print(f"   👉 {', '.join(corretoras_com_falha)}")
    else:
        print(f"\n🎉 Conectado com sucesso em 100% das corretoras ({total_corretoras}/{total_corretoras})!")

    if not dados_validos:
        print("⚠️ Nenhuma cotação válida capturada nesta rodada.")
        return

    # Agrupa dados por par de moedas
    dados_por_par = {}
    for item in dados_validos:
        par = item['symbol']
        if par not in dados_por_par:
            dados_por_par[par] = []
        dados_por_par[par].append(item)

    todas_oportunidades = []

    # Compara preços para calcular arbitragem
    for par, dados in dados_por_par.items():
        moeda_base = par.split('/')[0]

        for c_compra in dados:
            for c_venda in dados:
                if c_compra['exchange'] != c_venda['exchange']:
                    preco_compra = c_compra['ask']
                    preco_venda = c_venda['bid']

                    qtd_cripto = VALOR_INVESTIDO_USD / preco_compra
                    valor_bruto_venda = qtd_cripto * preco_venda
                    lucro_bruto_usd = valor_bruto_venda - VALOR_INVESTIDO_USD

                    custo_taxas_usd = VALOR_INVESTIDO_USD * (TAXA_ESTIMADA_TOTAL_PCT / 100)
                    lucro_liquido_usd = lucro_bruto_usd - custo_taxas_usd
                    pct_liquida = (lucro_liquido_usd / VALOR_INVESTIDO_USD) * 100

                    spread_bruto_pct = ((preco_venda - preco_compra) / preco_compra) * 100

                    if (SPREAD_MINIMO_PCT <= spread_bruto_pct <= SPREAD_MAXIMO_PCT) and (lucro_liquido_usd > 0):
                        tempo_est = estimar_tempo_operacao(spread_bruto_pct, moeda_base)
                        todas_oportunidades.append({
                            'par': par,
                            'moeda_base': moeda_base,
                            'compra_ex': c_compra['exchange'],
                            'compra_preco': preco_compra,
                            'venda_ex': c_venda['exchange'],
                            'venda_preco': preco_venda,
                            'qtd_cripto': qtd_cripto,
                            'lucro_bruto_usd': lucro_bruto_usd,
                            'custo_taxas_usd': custo_taxas_usd,
                            'lucro_liquido_usd': lucro_liquido_usd,
                            'spread_bruto_pct': spread_bruto_pct,
                            'pct_liquida': pct_liquida,
                            'tempo_estimado': tempo_est
                        })

    if todas_oportunidades:
        todas_oportunidades.sort(key=lambda x: x['lucro_liquido_usd'], reverse=True)
        
        oportunidades_filtradas = []
        moedas_processadas = set()

        for op in todas_oportunidades:
            if op['moeda_base'] not in moedas_processadas:
                oportunidades_filtradas.append(op)
                moedas_processadas.add(op['moeda_base'])

        msg = f"🚨 *OPORTUNIDADE DE ARBITRAGEM ({len(corretoras_com_sucesso)}/{total_corretoras} Corretoras)*\n"
        msg += f"💵 *Banca Base:* `${VALOR_INVESTIDO_USD:.2f} USDT`\n"
        msg += "=========================================\n\n"

        for i, op in enumerate(oportunidades_filtradas[:5], 1):
            msg += f"🔹 *#{i} {op['moeda_base']}* ({op['par']})\n"
            msg += f"🛒 *Comprar em:* `{op['compra_ex']}` ➔ *${op['compra_preco']:.4f}*\n"
            msg += f"📈 *Vender em:* `{op['venda_ex']}` ➔ *${op['venda_preco']:.4f}*\n"
            msg += f"📦 *Qtd Cripto:* `{op['qtd_cripto']:.4f} {op['moeda_base']}`\n"
            msg += f"💲 *Lucro Bruto:* `${op['lucro_bruto_usd']:.2f}` (+{op['spread_bruto_pct']:.2f}%)\n"
            msg += f"🏷️ *Taxas Est. (0.15%):* `-${op['custo_taxas_usd']:.2f}`\n"
            msg += f"💵 *LUCRO LÍQUIDO:* `+${op['lucro_liquido_usd']:.2f}` (*{op['pct_liquida']:+.2f}%*)\n"
            msg += f"⏳ *Janela Estimada:* {op['tempo_estimado']}\n"
            msg += "-----------------------------------------\n"

        print(f"\n📡 {len(oportunidades_filtradas)} oportunidades enviadas ao Telegram!")
        await enviar_mensagem_telegram(msg)
    else:
        print("\nℹ️ Sem spreads lucrativos nesta rodada.")


async def main():
    print(f"🚀 Bot de Arbitragem Iniciado! Monitorando {len(CORRETORAS_ALVO)} corretoras.")
    await enviar_mensagem_telegram(f"🤖 *Bot de Arbitragem Ativo!* Monitorando {len(CORRETORAS_ALVO)} corretoras.")
    while True:
        await executar_varredura()
        print(f"\n⏳ Próxima varredura em {INTERVALO_SEGUNDOS} segundos...\n" + "="*50)
        await asyncio.sleep(INTERVALO_SEGUNDOS)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot encerrado manualmente pelo usuário.")
