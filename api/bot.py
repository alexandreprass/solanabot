# api/bot.py (Versão para python-telegram-bot==13.15)

import os
import json
import logging
import time

try:
    import telegram
    # Diagnóstico simples para verificar a origem do módulo telegram importado
    print(f"--- DEBUG: Origem do módulo 'telegram' importado: {telegram.__file__ if hasattr(telegram, '__file__') else 'N/A'} ---")

    from telegram.ext import Dispatcher, CommandHandler, CallbackContext, MessageHandler, Filters
    from telegram import Update

    from solana.rpc.api import Client
    from solana.publickey import PublicKey
    import redis 
except ImportError as e:
    # Este print ajudará a ver se o erro de importação persiste mesmo com a v13.15
    print(f"!!! ERRO DE IMPORTAÇÃO CRÍTICO (esperando v13.15): {e} !!!")
    # Se o erro for sobre 'Dispatcher' não encontrado, então a v13.15 não foi instalada corretamente
    # ou o conflito da pasta 'telegram' em /var/task/ ainda existe.
    raise

# Configurar logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Carregar Segredos das Variáveis de Ambiente ---
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
SOLANA_RPC_URL = os.environ.get('SOLANA_RPC_URL')
UPSTASH_REDIS_URL = os.environ.get('UPSTASH_REDIS_URL')

# --- Inicializar Cliente Redis ---
kv_store = None
if UPSTASH_REDIS_URL:
    try:
        kv_store = redis.from_url(UPSTASH_REDIS_URL)
        kv_store.ping()
        logger.info("Conectado com sucesso ao Upstash Redis!")
    except Exception as e:
        logger.error(f"Não foi possível conectar ao Upstash Redis: {e}", exc_info=True)
else:
    logger.warning("UPSTASH_REDIS_URL não configurada.")


# --- Funções dos Comandos (Sintaxe v13.x) ---

def start_command(update: Update, context: CallbackContext):
    logger.info(f"Comando /start recebido do chat_id: {update.message.chat_id}")
    update.message.reply_text("Olá! Sou um bot para ranking de compras de tokens Solana. Use /help para ver os comandos.")

def help_command(update: Update, context: CallbackContext):
    logger.info(f"Comando /help recebido do chat_id: {update.message.chat_id}")
    help_text = """
    Comandos disponíveis:
    /cadastrartoken <endereco_do_token> - Registra um token.
    /ranking - Exibe o ranking de compras.
    /meutoken - Verifica o token registrado.
    """
    update.message.reply_text(help_text)

def register_token_command(update: Update, context: CallbackContext):
    chat_id = str(update.message.chat_id)
    logger.info(f"Comando /cadastrartoken recebido do chat_id: {chat_id} com args: {context.args}")
    if not context.args:
        update.message.reply_text("Uso: /cadastrartoken <endereco_do_token_solana>")
        return

    token_address = context.args[0]
    try:
        PublicKey(token_address)
    except ValueError:
        update.message.reply_text(f"Endereço de token inválido: {token_address}")
        return

    if kv_store:
        try:
            redis_key = f"token_config:{chat_id}"
            kv_store.set(redis_key, token_address)
            update.message.reply_text(f"Token {token_address} registrado para este grupo!")
        except Exception as e:
            logger.error(f"Erro ao salvar no Redis: {e}", exc_info=True)
            update.message.reply_text("Ocorreu um erro ao tentar registrar o token.")
    else:
        update.message.reply_text("AVISO: Serviço de armazenamento (Redis) não está configurado.")

def get_my_token_command(update: Update, context: CallbackContext):
    chat_id = str(update.message.chat_id)
    logger.info(f"Comando /meutoken recebido do chat_id: {chat_id}")
    if kv_store:
        try:
            redis_key = f"token_config:{chat_id}"
            token_address_bytes = kv_store.get(redis_key)
            if token_address_bytes:
                token_address = token_address_bytes.decode('utf-8')
                update.message.reply_text(f"O token registrado é: {token_address}")
            else:
                update.message.reply_text("Nenhum token registrado. Use /cadastrartoken.")
        except Exception as e:
            logger.error(f"Erro ao ler do Redis: {e}", exc_info=True)
            update.message.reply_text("Ocorreu um erro ao tentar verificar o token.")
    else:
        update.message.reply_text("AVISO: Serviço de armazenamento (Redis) não está configurado.")

def ranking_command(update: Update, context: CallbackContext):
    chat_id = str(update.message.chat_id)
    logger.info(f"Comando /ranking recebido do chat_id: {chat_id}")
    token_address = None

    if not kv_store:
        update.message.reply_text("AVISO: Serviço de armazenamento (Redis) não configurado.")
        return

    try:
        redis_key = f"token_config:{chat_id}"
        token_address_bytes = kv_store.get(redis_key)
        if token_address_bytes:
            token_address = token_address_bytes.decode('utf-8')
        else:
            update.message.reply_text("Nenhum token registrado. Use /cadastrartoken.")
            return
    except Exception as e:
        logger.error(f"Erro ao buscar token no Redis: {e}", exc_info=True)
        update.message.reply_text("Erro ao buscar configuração do token.")
        return

    update.message.reply_text(f"Processando ranking para {token_address[:10]}...")

    try:
        if not SOLANA_RPC_URL:
            update.message.reply_text("URL RPC da Solana não configurada no servidor.")
            return

        solana_client = Client(SOLANA_RPC_URL)
        token_pk = PublicKey(token_address)
        SIGNATURE_LIMIT = 50
        logger.info(f"Buscando {SIGNATURE_LIMIT} assinaturas para {token_address}...")
        resp = solana_client.get_signatures_for_address(token_pk, limit=SIGNATURE_LIMIT)

        if not resp or 'result' not in resp or not resp['result']:
            update.message.reply_text(f"Nenhuma transação recente para {token_address}.")
            return

        signatures_info = resp['result']
        logger.info(f"Encontradas {len(signatures_info)} assinaturas.")
        buyers = {}

        for sig_info in signatures_info:
            signature = sig_info['signature']
            try:
                tx_detail_resp = solana_client.get_transaction(signature, encoding="jsonParsed", commitment="confirmed", max_supported_transaction_version=0)
                tx_detail = tx_detail_resp.get('result')

                if not tx_detail or not tx_detail.get('meta') or tx_detail['meta'].get('err'):
                    continue

                meta = tx_detail['meta']
                accounts = tx_detail['transaction']['message']['accountKeys']
                pre_balances_sol = meta['preBalances']
                post_balances_sol = meta['postBalances']
                pre_token_balances = meta.get('preTokenBalances', [])
                post_token_balances = meta.get('postTokenBalances', [])

                if not accounts or not accounts[0]['signer']: continue
                potential_buyer_address = accounts[0]['pubkey']
                sol_spent_in_tx = 0
                token_received_in_tx = 0

                buyer_sol_idx = next((i for i, acc in enumerate(accounts) if acc['pubkey'] == potential_buyer_address), -1)

                if buyer_sol_idx != -1 and len(pre_balances_sol) > buyer_sol_idx and len(post_balances_sol) > buyer_sol_idx:
                    sol_before = pre_balances_sol[buyer_sol_idx]
                    sol_after = post_balances_sol[buyer_sol_idx]
                    if sol_before > sol_after:
                        sol_spent_in_tx = (sol_before - sol_after) / 10**9

                for tb_post in post_token_balances:
                    if tb_post.get('owner') == potential_buyer_address and tb_post.get('mint') == token_address:
                        amount_post_str = tb_post.get('uiTokenAmount', {}).get('uiAmountString', '0')
                        amount_post = float(amount_post_str) if amount_post_str else 0.0
                        amount_pre = 0.0
                        for tb_pre in pre_token_balances:
                            if tb_pre.get('owner') == potential_buyer_address and tb_pre.get('mint') == token_address:
                                amount_pre_str = tb_pre.get('uiTokenAmount', {}).get('uiAmountString', '0')
                                amount_pre = float(amount_pre_str) if amount_pre_str else 0.0
                                break
                        if amount_post > amount_pre:
                            token_received_in_tx = amount_post - amount_pre
                            break

                is_dex_tx = True # Placeholder - PRECISA DE LÓGICA REAL AQUI

                if sol_spent_in_tx > 0.00001 and token_received_in_tx > 0 and is_dex_tx:
                    buyers[potential_buyer_address] = buyers.get(potential_buyer_address, 0) + sol_spent_in_tx

            except Exception as e:
                logger.error(f"Erro ao processar tx {signature} no ranking: {e}", exc_info=True)
                continue

        if not buyers:
            update.message.reply_text("Nenhuma compra válida identificada.")
            return

        sorted_buyers = sorted(buyers.items(), key=lambda item: item[1], reverse=True)
        top_10 = sorted_buyers[:10]
        message = f"🏆 Top {len(top_10)} Compradores ({token_address[:6]}...) 🏆\n(Últimas {SIGNATURE_LIMIT} txs)\n\n"
        for i, (wallet, total_sol) in enumerate(top_10):
            short_wallet = f"{wallet[:6]}...{wallet[-4:]}"
            message += f"{i+1}. {short_wallet} - {total_sol:.4f} SOL\n"
        update.message.reply_text(message)

    except Exception as e:
        logger.error(f"Erro crítico no /ranking: {e}", exc_info=True)
        update.message.reply_text(f"Erro ao gerar ranking.")

# --- Configuração do Bot e Dispatcher (v13.x) ---
bot_instance = None
dispatcher = None

if not TELEGRAM_BOT_TOKEN:
    logger.critical("TELEGRAM_BOT_TOKEN não encontrado! Bot não pode iniciar.")
else:
    try:
        bot_instance = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
        dispatcher = Dispatcher(bot_instance, None, workers=0, use_context=True)
        dispatcher.add_handler(CommandHandler("start", start_command))
        dispatcher.add_handler(CommandHandler("help", help_command))
        dispatcher.add_handler(CommandHandler("cadastrartoken", register_token_command))
        dispatcher.add_handler(CommandHandler("meutoken", get_my_token_command))
        dispatcher.add_handler(CommandHandler("ranking", ranking_command))
        logger.info("Bot e Dispatcher (v13.x) inicializados.")
    except Exception as e:
        logger.critical(f"Erro ao inicializar Bot ou Dispatcher (v13.x): {e}", exc_info=True)
        bot_instance = None
        dispatcher = None


# --- Handler Principal da Vercel ---
def handler(event, context_aws_lambda_placeholder):
    if not dispatcher or not bot_instance:
        logger.error("Dispatcher ou Bot não inicializado no handler.")
        return {'statusCode': 500, 'body': json.dumps({'error': 'Bot not configured'})}

    try:
        if isinstance(event, str):
            update_json = json.loads(event)
        elif isinstance(event, dict) and 'body' in event:
            if isinstance(event['body'], str):
                update_json = json.loads(event['body'])
            else:
                update_json = event['body']
        else:
            update_json = event

        update = Update.de_json(update_json, bot_instance)
        dispatcher.process_update(update)
        return {'statusCode': 200, 'body': json.dumps({'message': 'Update processed'})}
    except Exception as e:
        logger.error(f"Erro no handler principal: {e}", exc_info=True)
        return {'statusCode': 500, 'body': json.dumps({'error': f'Internal server error: {str(e)}'})}
