# api/bot.py

import os
import json
import logging # Para logs na Vercel
import time # Para possíveis delays

import telegram
from telegram.ext import Dispatcher, CommandHandler, CallbackContext, MessageHandler, Filters
from telegram import Update

from solana.rpc.api import Client
from solana.publickey import PublicKey
# from solana.rpc.types import TokenAccountOpts # Se precisar buscar contas de token específicas

# Configurar logging básico para ver saídas nos logs da Vercel
logging.basicConfig(level=logging.INFO)

# --- Carregar Segredos das Variáveis de Ambiente ---
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
SOLANA_RPC_URL = os.environ.get('SOLANA_RPC_URL')
# Exemplo para Vercel KV (ou outro DBaaS como Upstash Redis)
# Se usar Vercel KV, você interage via API HTTP, não uma lib de cliente direto geralmente.
# Para Upstash Redis:
# UPSTASH_REDIS_URL = os.environ.get('UPSTASH_REDIS_URL')
# import redis
# if UPSTASH_REDIS_URL:
#     kv_store = redis.from_url(UPSTASH_REDIS_URL)
# else:
#     kv_store = None # Ou um fallback para memória se rodar localmente e não quiser DB

# --- Lógica para o Armazenamento de Configuração (Chat ID -> Token Address) ---
# Esta é uma implementação MUITO SIMPLES em memória para demonstração.
# NA VERCEL, ISSO NÃO PERSISTIRÁ ENTRE INVOCAÇÕES!
# VOCÊ PRECISA USAR VERCEL KV, UPSTASH, SUPABASE, ETC.
# Exemplo conceitual se fosse um dicionário (NÃO FAÇA ASSIM NA VERCEL PARA DADOS PERSISTENTES):
# chat_token_config = {}

# Para Vercel KV: você faria requisições HTTP para a API do Vercel KV.
# Ex: GET https://kv.vercel.com/get/[KEY]?token=[KV_READ_ACCESS_TOKEN]
#     POST https://kv.vercel.com/set/[KEY]?token=[KV_WRITE_ACCESS_TOKEN]
# Você precisará de 'requests' lib: pip install requests

# --- Funções dos Comandos ---

def start_command(update: Update, context: CallbackContext):
    update.message.reply_text("Olá! Sou um bot para ranking de compras de tokens Solana. Use /help para ver os comandos.")

def help_command(update: Update, context: CallbackContext):
    help_text = """
    Comandos disponíveis:
    /cadastrartoken <endereco_do_token> - Registra um token para monitoramento neste grupo.
    /ranking - Exibe o ranking de compras para o token registrado.
    /meutoken - Verifica qual token está atualmente registrado para este grupo.
    """
    update.message.reply_text(help_text)

def register_token_command(update: Update, context: CallbackContext):
    chat_id = str(update.message.chat_id)
    if not context.args:
        update.message.reply_text("Uso: /cadastrartoken <endereco_do_token_solana>")
        return

    token_address = context.args[0]
    try:
        # Validar superficialmente o endereço do token
        PublicKey(token_address)
    except ValueError:
        update.message.reply_text(f"Endereço de token inválido: {token_address}")
        return

    # LÓGICA DE ARMAZENAMENTO NO KV STORE (Exemplo com Upstash Redis)
    # if kv_store:
    #     kv_store.set(f"token_config:{chat_id}", token_address)
    #     update.message.reply_text(f"Token {token_address} registrado para este grupo!")
    # else:
    #     # Fallback para demonstração (não persistente na Vercel)
    #     # chat_token_config[chat_id] = token_address
    #     update.message.reply_text("AVISO: Armazenamento KV não configurado. O token será lembrado apenas temporariamente (não na Vercel).")
    update.message.reply_text(f"Simulação: Token {token_address} registrado para o chat {chat_id}. Implemente o KV Store!")
    logging.info(f"Token {token_address} registrado para chat_id {chat_id}")


def get_my_token_command(update: Update, context: CallbackContext):
    chat_id = str(update.message.chat_id)
    # LÓGICA DE LEITURA DO KV STORE
    # token_address_bytes = kv_store.get(f"token_config:{chat_id}") if kv_store else None
    # if token_address_bytes:
    #     token_address = token_address_bytes.decode('utf-8')
    #     update.message.reply_text(f"O token atualmente registrado para este grupo é: {token_address}")
    # else:
    #     # Fallback
    #     # token_address = chat_token_config.get(chat_id)
    #     # if token_address:
    #     #     update.message.reply_text(f"Token (temporário): {token_address}")
    #     # else:
    #     #     update.message.reply_text("Nenhum token registrado para este grupo. Use /cadastrartoken.")
    update.message.reply_text(f"Simulação: Verificando token para o chat {chat_id}. Implemente o KV Store!")


def ranking_command(update: Update, context: CallbackContext):
    chat_id = str(update.message.chat_id)
    update.message.reply_text("Processando o ranking... Isso pode levar um momento.")

    # 1. Obter o token_address do KV Store
    # token_address_bytes = kv_store.get(f"token_config:{chat_id}") if kv_store else None
    # if not token_address_bytes:
    #     # Fallback
    #     # token_address = chat_token_config.get(chat_id)
    #     # if not token_address:
    #     #     update.message.reply_text("Nenhum token registrado para este grupo. Use /cadastrartoken.")
    #     #     return
    #     update.message.reply_text("Simulação: Token não encontrado. Implemente KV Store!")
    #     return
    # else:
    #     token_address = token_address_bytes.decode('utf-8')
    
    # Para teste, fixar um token se não tiver KV Store ainda:
    token_address = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263" # Exemplo: WIF token, apenas para estrutura
    logging.info(f"Gerando ranking para token {token_address} no chat {chat_id}")

    try:
        if not SOLANA_RPC_URL:
            update.message.reply_text("URL RPC da Solana não configurada.")
            logging.error("SOLANA_RPC_URL não está configurada.")
            return

        solana_client = Client(SOLANA_RPC_URL)
        token_pk = PublicKey(token_address)

        # Limite de assinaturas para buscar (IMPORTANTE para Vercel)
        # Um valor muito alto pode exceder o tempo de execução da Vercel (ex: 10s no Hobby).
        SIGNATURE_LIMIT = 50 # COMECE COM VALORES BAIXOS (10-50) E AUMENTE COM CUIDADO!
        logging.info(f"Buscando últimas {SIGNATURE_LIMIT} assinaturas para {token_address}...")

        resp = solana_client.get_signatures_for_address(token_pk, limit=SIGNATURE_LIMIT)
        
        if not resp or 'result' not in resp or not resp['result']:
            update.message.reply_text(f"Nenhuma transação recente encontrada para o token {token_address}.")
            logging.info(f"Nenhuma assinatura encontrada para {token_address}.")
            return
        
        signatures_info = resp['result']
        logging.info(f"Encontradas {len(signatures_info)} assinaturas.")

        buyers = {}  # {'wallet_address': total_sol_spent}
        processed_count = 0

        for sig_info in signatures_info:
            signature = sig_info['signature']
            # Pequeno delay para não sobrecarregar o RPC, especialmente nós públicos ou com limites
            # time.sleep(0.05) # 50ms; ajuste ou remova se estiver usando um RPC robusto como QuickNode

            try:
                # Usar commitment 'confirmed' ou 'finalized'. 'processed' pode ser revertido.
                tx_detail_resp = solana_client.get_transaction(signature, encoding="jsonParsed", commitment="confirmed", max_supported_transaction_version=0)
                tx_detail = tx_detail_resp.get('result')

                if not tx_detail or not tx_detail.get('meta'):
                    logging.warning(f"Detalhes da transação ou meta não encontrados para {signature}")
                    continue

                meta = tx_detail['meta']
                err = meta.get('err')
                if err:
                    logging.info(f"Transação {signature} falhou: {err}")
                    continue # Pular transações com erro

                log_messages = meta.get('logMessages', [])

                # **LÓGICA DE IDENTIFICAÇÃO DE COMPRA (COMPLEXA E PRECISA SER ROBUSTA)**
                # Esta é a parte mais difícil. Você precisa:
                # 1. Identificar interações com Programas de DEX (Raydium, Orca, Jupiter etc.).
                #    Pode ser por ID do programa nas instruções ou por logs específicos.
                # 2. Determinar quem é o comprador (geralmente o pagador da taxa ou o originador da troca).
                # 3. Analisar `preBalances`, `postBalances` (para SOL) e `preTokenBalances`, `postTokenBalances` (para o token e wSOL)
                #    para confirmar a direção da troca e o valor de SOL gasto.
                #
                # Exemplo MUITO SIMPLIFICADO e INCOMPLETO:
                # Procurar por uma diminuição de SOL e um aumento do token rastreado para uma carteira.

                accounts = tx_detail['transaction']['message']['accountKeys']
                pre_balances_sol = meta['preBalances']
                post_balances_sol = meta['postBalances']
                pre_token_balances = meta.get('preTokenBalances', [])
                post_token_balances = meta.get('postTokenBalances', [])

                # Tentar identificar o comprador (geralmente o primeiro signatário/feePayer)
                if not accounts[0]['signer']: continue # Fee payer precisa ser signer
                potential_buyer_address = accounts[0]['pubkey']

                sol_spent_in_tx = 0
                token_received_in_tx = 0

                # Mudança de SOL para o potential_buyer
                buyer_sol_idx = -1
                for i, acc in enumerate(accounts):
                    if acc['pubkey'] == potential_buyer_address:
                        buyer_sol_idx = i
                        break
                
                if buyer_sol_idx != -1:
                    sol_before = pre_balances_sol[buyer_sol_idx]
                    sol_after = post_balances_sol[buyer_sol_idx]
                    if sol_before > sol_after: # SOL diminuiu
                        sol_spent_in_tx = (sol_before - sol_after) / 10**9 # Lamports to SOL

                # Mudança do token para o potential_buyer
                for tb_post in post_token_balances:
                    if tb_post['owner'] == potential_buyer_address and tb_post['mint'] == token_address:
                        amount_post = float(tb_post.get('uiTokenAmount', {}).get('uiAmountString', '0'))
                        amount_pre = 0
                        for tb_pre in pre_token_balances:
                            if tb_pre['owner'] == potential_buyer_address and tb_pre['mint'] == token_address:
                                amount_pre = float(tb_pre.get('uiTokenAmount', {}).get('uiAmountString', '0'))
                                break
                        if amount_post > amount_pre: # Token aumentou
                            token_received_in_tx = amount_post - amount_pre
                            break # Assume uma entrada do token por transação para simplificar

                # Considerar uma compra se SOL diminuiu E o token específico aumentou para o comprador
                # E algum programa de DEX foi envolvido (verificar log_messages por IDs de programas de DEX)
                # Ex: RAYDIUM_PROGRAM_ID = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
                # is_dex_tx = any(RAYDIUM_PROGRAM_ID in log for log in log_messages) # Simplificação
                is_dex_tx = True # REMOVER! Precisa de lógica real aqui.

                if sol_spent_in_tx > 0.0001 and token_received_in_tx > 0 and is_dex_tx: # Adicionar valor mínimo de SOL
                    buyers[potential_buyer_address] = buyers.get(potential_buyer_address, 0) + sol_spent_in_tx
                    logging.info(f"Compra detectada: {potential_buyer_address} comprou {token_received_in_tx} do token gastando {sol_spent_in_tx} SOL na tx {signature}")
                
                processed_count += 1

            except Exception as e:
                logging.error(f"Erro ao processar tx {signature}: {e}", exc_info=True)
                continue
        
        logging.info(f"Total de transações analisadas após filtro inicial: {processed_count}")
        if not buyers:
            update.message.reply_text("Nenhuma compra válida identificada nas transações recentes analisadas.")
            return

        sorted_buyers = sorted(buyers.items(), key=lambda item: item[1], reverse=True)
        top_10 = sorted_buyers[:10]

        message = f"🏆 Top {len(top_10)} Compradores do Token ({token_address[:6]}...) 🏆\n(Analisadas {len(signatures_info)} assinaturas recentes)\n\n"
        for i, (wallet, total_sol) in enumerate(top_10):
            short_wallet = f"{wallet[:6]}...{wallet[-4:]}"
            message += f"{i+1}. {short_wallet} - {total_sol:.4f} SOL\n"

        update.message.reply_text(message)

    except Exception as e:
        logging.error(f"Erro crítico no comando /ranking: {e}", exc_info=True)
        update.message.reply_text(f"Ocorreu um erro ao gerar o ranking. Tente novamente mais tarde.")


# --- Configuração do Bot e Dispatcher ---
if not TELEGRAM_BOT_TOKEN:
    logging.critical("TELEGRAM_BOT_TOKEN não encontrado nas variáveis de ambiente!")
    # Em um cenário real, você não deveria nem tentar iniciar o bot.
    # Aqui, apenas para permitir que o arquivo seja importado sem erro imediato.
    bot_instance = None
    dispatcher = None
else:
    bot_instance = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
    dispatcher = Dispatcher(bot_instance, None, workers=0, use_context=True) # workers=0 para serverless

    # Adicionar Handlers
    dispatcher.add_handler(CommandHandler("start", start_command))
    dispatcher.add_handler(CommandHandler("help", help_command))
    dispatcher.add_handler(CommandHandler("cadastrartoken", register_token_command))
    dispatcher.add_handler(CommandHandler("meutoken", get_my_token_command))
    dispatcher.add_handler(CommandHandler("ranking", ranking_command))
    # Adicione um handler para mensagens desconhecidas se desejar
    # dispatcher.add_handler(MessageHandler(Filters.command, unknown_command_handler))


# --- Handler Principal da Vercel ---
# A Vercel espera uma função chamada 'handler' no arquivo especificado (ex: api/bot.py)
def handler(event, context): # Os nomes 'event' e 'context' são convenções do AWS Lambda
    # Para Vercel, 'event' geralmente contém o corpo da requisição HTTP (como um dict se JSON)
    # e 'context' pode não ser tão relevante quanto no Lambda.

    if not dispatcher:
        logging.error("Dispatcher não inicializado. Verifique o token do Telegram.")
        return {'statusCode': 500, 'body': json.dumps({'error': 'Bot not configured'})}
    try:
        # Vercel pode passar o corpo da requisição de diferentes formas.
        # Tente decodificar o corpo se for uma string JSON.
        if isinstance(event, str):
            body_dict = json.loads(event)
        elif isinstance(event, dict) and 'body' in event: # Comum se Vercel emula API Gateway
             # Se o corpo já é um dict, não precisa json.loads(event['body'])
             # Se for string, precisa:
            if isinstance(event['body'], str):
                body_dict = json.loads(event['body'])
            else:
                body_dict = event['body'] # Assume que já é um dict
        else: # Assume que 'event' já é o update JSON como dict
            body_dict = event

        update = Update.de_json(body_dict, bot_instance)
        dispatcher.process_update(update)

        return {
            'statusCode': 200,
            'body': json.dumps({'message': 'Update processed'})
        }
    except json.JSONDecodeError as e:
        logging.error(f"Erro ao decodificar JSON: {e}. Request body: {event}")
        return {'statusCode': 400, 'body': json.dumps({'error': 'Bad JSON format'})}
    except Exception as e:
        logging.error(f"Erro no handler principal: {e}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f'Internal server error: {str(e)}'})
        }

# --- Para registrar o webhook (execute uma vez localmente ou via script) ---
# Necessário para o Telegram saber para onde enviar os updates.
def set_webhook():
    if not bot_instance:
        print("Instância do Bot não criada. Verifique o token.")
        return

    # Substitua pelo seu domínio Vercel real após o deploy
    VERCEL_PROJECT_URL = os.environ.get("VERCEL_URL") # Vercel injeta esta variável em builds
    if VERCEL_PROJECT_URL:
        # O path /api/bot deve corresponder à localização do seu arquivo handler
        webhook_url = f"https://{VERCEL_PROJECT_URL}/api/bot"
        if bot_instance.set_webhook(webhook_url):
            print(f"Webhook configurado para: {webhook_url}")
        else:
            print(f"Falha ao configurar o webhook para: {webhook_url}")
    else:
        print("Variável VERCEL_URL não encontrada. Configure o webhook manualmente ou após o deploy.")
        print("Exemplo: https://api.telegram.org/botSEU_TOKEN/setWebhook?url=https://SEU_PROJETO.vercel.app/api/bot")

# if __name__ == "__main__":
    # Este bloco é útil para testes locais, mas não será executado na Vercel.
    # Para testar localmente com polling (não webhook):
    # print("Iniciando bot com polling para teste local...")
    # updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)
    # dp = updater.dispatcher
    # # Adicionar handlers aqui também se quiser testar com polling
    # dp.add_handler(CommandHandler("start", start_command))
    # dp.add_handler(CommandHandler("cadastrartoken", register_token_command))
    # dp.add_handler(CommandHandler("ranking", ranking_command))
    # updater.start_polling()
    # updater.idle()

    # Para configurar o webhook:
    # set_webhook()
