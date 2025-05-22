# api/bot.py

import os
import json
import logging
import time

import telegram
from telegram.ext import Dispatcher, CommandHandler, CallbackContext, MessageHandler, Filters
from telegram import Update

from solana.rpc.api import Client
from solana.publickey import PublicKey

import redis # Importar a biblioteca Redis

# Configurar logging
logging.basicConfig(level=logging.INFO)

# --- Carregar Segredos das Variáveis de Ambiente ---
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
SOLANA_RPC_URL = os.environ.get('SOLANA_RPC_URL')
UPSTASH_REDIS_URL = os.environ.get('UPSTASH_REDIS_URL') # Sua NOVA URL do Upstash Redis

# --- Inicializar Cliente Redis ---
kv_store = None
if UPSTASH_REDIS_URL:
    try:
        # A URL do Upstash já inclui 'rediss://' para SSL
        kv_store = redis.from_url(UPSTASH_REDIS_URL)
        # Testar a conexão (opcional, mas bom para depuração inicial)
        kv_store.ping()
        logging.info("Conectado com sucesso ao Upstash Redis!")
    except redis.exceptions.ConnectionError as e:
        logging.error(f"Não foi possível conectar ao Upstash Redis: {e}", exc_info=True)
        kv_store = None # Garante que não tentaremos usar um cliente que falhou ao conectar
    except Exception as e:
        logging.error(f"Erro inesperado ao inicializar o cliente Redis: {e}", exc_info=True)
        kv_store = None
else:
    logging.warning("UPSTASH_REDIS_URL não configurada. O bot não poderá persistir o cadastro de tokens.")


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
        PublicKey(token_address) # Validação superficial
    except ValueError:
        update.message.reply_text(f"Endereço de token inválido: {token_address}")
        return

    if kv_store:
        try:
            # Chave no Redis: prefixo para organização + chat_id
            redis_key = f"token_config:{chat_id}"
            kv_store.set(redis_key, token_address)
            update.message.reply_text(f"Token {token_address} registrado para este grupo!")
            logging.info(f"Token {token_address} salvo no Redis para chat_id {chat_id} (key: {redis_key})")
        except redis.exceptions.RedisError as e:
            logging.error(f"Erro ao salvar no Redis para chat_id {chat_id}: {e}", exc_info=True)
            update.message.reply_text("Ocorreu um erro ao tentar registrar o token. Tente novamente mais tarde.")
        except Exception as e:
            logging.error(f"Erro inesperado em register_token_command com Redis: {e}", exc_info=True)
            update.message.reply_text("Ocorreu um erro inesperado. Tente novamente mais tarde.")
    else:
        update.message.reply_text("AVISO: Serviço de armazenamento (Redis) não está configurado ou falhou ao conectar. O token não pôde ser salvo permanentemente.")
        logging.warning(f"Tentativa de registrar token {token_address} para chat_id {chat_id} sem conexão Redis.")

def get_my_token_command(update: Update, context: CallbackContext):
    chat_id = str(update.message.chat_id)
    if kv_store:
        try:
            redis_key = f"token_config:{chat_id}"
            token_address_bytes = kv_store.get(redis_key)
            if token_address_bytes:
                token_address = token_address_bytes.decode('utf-8')
                update.message.reply_text(f"O token atualmente registrado para este grupo é: {token_address}")
                logging.info(f"Token {token_address} recuperado do Redis para chat_id {chat_id} (key: {redis_key})")
            else:
                update.message.reply_text("Nenhum token registrado para este grupo. Use /cadastrartoken.")
                logging.info(f"Nenhum token encontrado no Redis para chat_id {chat_id} (key: {redis_key})")
        except redis.exceptions.RedisError as e:
            logging.error(f"Erro ao ler do Redis para chat_id {chat_id}: {e}", exc_info=True)
            update.message.reply_text("Ocorreu um erro ao tentar verificar o token. Tente novamente mais tarde.")
        except Exception as e:
            logging.error(f"Erro inesperado em get_my_token_command com Redis: {e}", exc_info=True)
            update.message.reply_text("Ocorreu um erro inesperado. Tente novamente mais tarde.")
    else:
        update.message.reply_text("AVISO: Serviço de armazenamento (Redis) não está configurado ou falhou ao conectar. Não é possível verificar o token.")

def ranking_command(update: Update, context: CallbackContext):
    chat_id = str(update.message.chat_id)
    token_address = None

    if kv_store:
        try:
            redis_key = f"token_config:{chat_id}"
            token_address_bytes = kv_store.get(redis_key)
            if token_address_bytes:
                token_address = token_address_bytes.decode('utf-8')
                logging.info(f"Token {token_address} recuperado do Redis para ranking no chat_id {chat_id}")
            else:
                update.message.reply_text("Nenhum token registrado para este grupo. Use /cadastrartoken primeiro.")
                return
        except redis.exceptions.RedisError as e:
            logging.error(f"Erro ao buscar token no Redis para ranking (chat_id {chat_id}): {e}", exc_info=True)
            update.message.reply_text("Erro ao buscar configuração do token. Tente novamente.")
            return
        except Exception as e:
            logging.error(f"Erro inesperado ao buscar token no Redis para ranking (chat_id {chat_id}): {e}", exc_info=True)
            update.message.reply_text("Erro inesperado. Tente novamente.")
            return
    else:
        update.message.reply_text("AVISO: Serviço de armazenamento (Redis) não configurado. Não é possível gerar ranking.")
        return

    update.message.reply_text(f"Processando o ranking para o token {token_address[:10]}... Isso pode levar um momento.")
    logging.info(f"Gerando ranking para token {token_address} no chat {chat_id}")

    try:
        if not SOLANA_RPC_URL:
            update.message.reply_text("URL RPC da Solana não configurada.")
            logging.error("SOLANA_RPC_URL não está configurada.")
            return

        solana_client = Client(SOLANA_RPC_URL)
        token_pk = PublicKey(token_address)
        SIGNATURE_LIMIT = 50 # Mantenha baixo para Vercel
        logging.info(f"Buscando últimas {SIGNATURE_LIMIT} assinaturas para {token_address}...")

        resp = solana_client.get_signatures_for_address(token_pk, limit=SIGNATURE_LIMIT)
        
        if not resp or 'result' not in resp or not resp['result']:
            update.message.reply_text(f"Nenhuma transação recente encontrada para o token {token_address}.")
            return
        
        signatures_info = resp['result']
        logging.info(f"Encontradas {len(signatures_info)} assinaturas.")
        buyers = {}
        processed_count = 0

        for sig_info in signatures_info:
            # ... (Lógica de análise de transação - MANTENHA A MESMA LÓGICA COMPLEXA E CUIDADOSA DA VERSÃO ANTERIOR)
            # Esta parte é crucial e demorada. Certifique-se de que ela é o mais otimizada possível.
            # Lembre-se das limitações de tempo da Vercel.
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
                
                if buyer_sol_idx != -1:
                    sol_before = pre_balances_sol[buyer_sol_idx]
                    sol_after = post_balances_sol[buyer_sol_idx]
                    if sol_before > sol_after:
                        sol_spent_in_tx = (sol_before - sol_after) / 10**9

                for tb_post in post_token_balances:
                    if tb_post['owner'] == potential_buyer_address and tb_post['mint'] == token_address:
                        amount_post = float(tb_post.get('uiTokenAmount', {}).get('uiAmountString', '0'))
                        amount_pre = 0
                        for tb_pre in pre_token_balances:
                            if tb_pre['owner'] == potential_buyer_address and tb_pre['mint'] == token_address:
                                amount_pre = float(tb_pre.get('uiTokenAmount', {}).get('uiAmountString', '0'))
                                break
                        if amount_post > amount_pre:
                            token_received_in_tx = amount_post - amount_pre
                            break
                
                # PRECISA DE UMA LÓGICA MELHOR PARA is_dex_tx (verificar logs de programas de DEX)
                is_dex_tx = True # REMOVER E IMPLEMENTAR CORRETAMENTE

                if sol_spent_in_tx > 0.0001 and token_received_in_tx > 0 and is_dex_tx:
                    buyers[potential_buyer_address] = buyers.get(potential_buyer_address, 0) + sol_spent_in_tx
                
                processed_count += 1
            except Exception as e:
                logging.error(f"Erro ao processar tx {signature} no ranking: {e}", exc_info=True)
                continue # Pula para a próxima transação

        logging.info(f"Total de transações analisadas no ranking: {processed_count}")
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

# --- Configuração do Bot e Dispatcher (semelhante à versão anterior) ---
if not TELEGRAM_BOT_TOKEN:
    logging.critical("TELEGRAM_BOT_TOKEN não encontrado!")
    bot_instance = None
    dispatcher = None
else:
    bot_instance = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
    # workers=0 é importante para ambientes serverless como Vercel
    dispatcher = Dispatcher(bot_instance, None, workers=0, use_context=True)
    dispatcher.add_handler(CommandHandler("start", start_command))
    dispatcher.add_handler(CommandHandler("help", help_command))
    dispatcher.add_handler(CommandHandler("cadastrartoken", register_token_command))
    dispatcher.add_handler(CommandHandler("meutoken", get_my_token_command))
    dispatcher.add_handler(CommandHandler("ranking", ranking_command))

# --- Handler Principal da Vercel (semelhante à versão anterior) ---
def handler(event, context):
    if not dispatcher:
        logging.error("Dispatcher não inicializado.")
        return {'statusCode': 500, 'body': json.dumps({'error': 'Bot not configured'})}
    try:
        # ... (lógica para extrair update_json de 'event' - mantenha a da versão anterior)
        if isinstance(event, str): body_dict = json.loads(event)
        elif isinstance(event, dict) and 'body' in event:
            body_dict = json.loads(event['body']) if isinstance(event['body'], str) else event['body']
        else: body_dict = event
        
        update = Update.de_json(body_dict, bot_instance)
        dispatcher.process_update(update)
        return {'statusCode': 200, 'body': json.dumps({'message': 'Update processed'})}
    except Exception as e:
        logging.error(f"Erro no handler principal: {e}", exc_info=True)
        return {'statusCode': 500, 'body': json.dumps({'error': f'Internal server error: {str(e)}'})}

# --- set_webhook (opcional, para rodar localmente uma vez) ---
# (mantenha a função set_webhook da versão anterior, se precisar)
