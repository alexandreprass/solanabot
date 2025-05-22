# api/bot.py (Tentativa de deletar /var/task/telegram e usar PTB v13.15)

import os
import sys
import shutil # Para remover diretórios
import json
import logging
import time

# --- TENTATIVA DE DELETAR A PASTA /var/task/telegram CONFLITANTE ---
CONFLICTING_TELEGRAM_PATH = "/var/task/telegram"
print(f"--- INÍCIO DO SCRIPT: Tentando resolver conflito de 'telegram' ---")
if os.path.exists(CONFLICTING_TELEGRAM_PATH):
    print(f"Encontrada a entrada conflitante: {CONFLICTING_TELEGRAM_PATH}")
    if os.path.isdir(CONFLICTING_TELEGRAM_PATH):
        print(f"É um diretório. Tentando remover com shutil.rmtree...")
        try:
            shutil.rmtree(CONFLICTING_TELEGRAM_PATH)
            print(f"SUCESSO ao remover o diretório: {CONFLICTING_TELEGRAM_PATH}")
            if os.path.exists(CONFLICTING_TELEGRAM_PATH):
                print(f"!!! AVISO: {CONFLICTING_TELEGRAM_PATH} ainda existe após shutil.rmtree !!!")
            else:
                print(f"Confirmado: {CONFLICTING_TELEGRAM_PATH} foi removido.")
        except Exception as e_rmtree:
            print(f"!!! ERRO ao tentar remover {CONFLICTING_TELEGRAM_PATH} com shutil.rmtree: {e_rmtree} !!!")
    elif os.path.isfile(CONFLICTING_TELEGRAM_PATH):
        print(f"É um arquivo. Tentando remover com os.remove...")
        try:
            os.remove(CONFLICTING_TELEGRAM_PATH)
            print(f"SUCESSO ao remover o arquivo: {CONFLICTING_TELEGRAM_PATH}")
        except Exception as e_remove:
             print(f"!!! ERRO ao tentar remover o arquivo {CONFLICTING_TELEGRAM_PATH}: {e_remove} !!!")
    else:
        print(f"'{CONFLICTING_TELEGRAM_PATH}' não é diretório nem arquivo regular. Não foi possível remover.")
else:
    print(f"Nenhuma entrada conflitante encontrada em: {CONFLICTING_TELEGRAM_PATH} (Isso é bom).")

print(f"\n--- Python sys.path ATUAL: {sys.path} ---")
# --- FIM DA TENTATIVA DE DELEÇÃO ---

try:
    print("\n--- Tentando importar bibliotecas principais ---")
    import telegram
    print(f"--- DEBUG: Origem do módulo 'telegram' importado: {telegram.__file__ if hasattr(telegram, '__file__') else 'N/A'} ---")

    from telegram.ext import Dispatcher, CommandHandler, CallbackContext, MessageHandler, Filters
    from telegram import Update
    print("--- DEBUG: Componentes de telegram.ext importados com sucesso! ---")

    print("--- DEBUG: Tentando importar Solana ---")
    from solana.rpc.api import Client
    from solana.publickey import PublicKey
    print("--- DEBUG: Solana importado com sucesso ---")

    import redis 
    print("--- DEBUG: Redis importado com sucesso ---")

except ImportError as e:
    print(f"!!! ERRO DE IMPORTAÇÃO CRÍTICO: {e} !!!")
    raise
except Exception as e_init:
    print(f"!!! ERRO GERAL DURANTE IMPORTAÇÕES INICIAIS: {e_init} !!!")
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
# (Cole aqui as mesmas funções de comando start_command, help_command, etc., que usamos para v13.15)

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
    if not context.args:
        update.message.reply_text("Uso: /cadastrartoken <endereco_do_token_solana>")
        return
    token_address = context.args[0]
    try: PublicKey(token_address)
    except Exception: update.message.reply_text(f"Endereço de token Solana inválido: {token_address}"); return
    if kv_store:
        try: kv_store.set(f"token_config:{chat_id}", token_address); update.message.reply_text(f"Token {token_address} registrado!")
        except Exception as e: logger.error(f"Erro Redis: {e}"); update.message.reply_text("Erro ao registrar.")
    else: update.message.reply_text("AVISO: Armazenamento Redis não configurado.")

def get_my_token_command(update: Update, context: CallbackContext):
    chat_id = str(update.message.chat_id)
    if kv_store:
        try:
            val = kv_store.get(f"token_config:{chat_id}")
            if val: update.message.reply_text(f"Token registrado: {val.decode('utf-8')}")
            else: update.message.reply_text("Nenhum token registrado.")
        except Exception as e: logger.error(f"Erro Redis: {e}"); update.message.reply_text("Erro ao verificar token.")
    else: update.message.reply_text("AVISO: Armazenamento Redis não configurado.")

def ranking_command(update: Update, context: CallbackContext):
    chat_id = str(update.message.chat_id)
    if not kv_store: update.message.reply_text("AVISO: Armazenamento Redis não configurado."); return
    try:
        val = kv_store.get(f"token_config:{chat_id}")
        if not val: update.message.reply_text("Nenhum token registrado."); return
        token_address = val.decode('utf-8')
    except Exception as e: logger.error(f"Erro Redis: {e}"); update.message.reply_text("Erro config token."); return

    update.message.reply_text(f"Processando ranking para {token_address[:10]}...")
    try:
        if not SOLANA_RPC_URL: update.message.reply_text("URL RPC Solana não configurada."); return
        solana_client = Client(SOLANA_RPC_URL)
        token_pk = PublicKey(token_address)
        SIGNATURE_LIMIT = 50
        resp = solana_client.get_signatures_for_address(token_pk, limit=SIGNATURE_LIMIT)
        if not resp or 'result' not in resp or not resp['result']: update.message.reply_text(f"Nenhuma tx recente para {token_address}."); return

        signatures_info = resp['result']
        buyers = {}
        for sig_info in signatures_info:
            try:
                tx_detail_resp = solana_client.get_transaction(sig_info['signature'], encoding="jsonParsed", commitment="confirmed", max_supported_transaction_version=0)
                tx_detail = tx_detail_resp.get('result')
                if not tx_detail or not tx_detail.get('meta') or tx_detail['meta'].get('err'): continue
                meta, accounts = tx_detail['meta'], tx_detail['transaction']['message']['accountKeys']
                if not accounts or not accounts[0]['signer']: continue
                potential_buyer, sol_spent, token_received = accounts[0]['pubkey'], 0, 0
                idx = next((i for i, acc in enumerate(accounts) if acc['pubkey'] == potential_buyer), -1)
                if idx!=-1 and len(meta['preBalances'])>idx and len(meta['postBalances'])>idx and meta['preBalances'][idx]>meta['postBalances'][idx]:
                    sol_spent=(meta['preBalances'][idx]-meta['postBalances'][idx])/10**9
                for tb_post in meta.get('postTokenBalances',[]):
                    if tb_post.get('owner')==potential_buyer and tb_post.get('mint')==token_address:
                        post_amt=float(tb_post.get('uiTokenAmount',{}).get('uiAmountString','0') or '0')
                        pre_amt=0.0
                        for tb_pre in meta.get('preTokenBalances',[]):
                            if tb_pre.get('owner')==potential_buyer and tb_pre.get('mint')==token_address:
                                pre_amt=float(tb_pre.get('uiTokenAmount',{}).get('uiAmountString','0') or '0'); break
                        if post_amt>pre_amt: token_received=post_amt-pre_amt; break
                if sol_spent>1e-5 and token_received>0: buyers[potential_buyer]=buyers.get(potential_buyer,0)+sol_spent
            except Exception as e_tx: logger.error(f"Erro tx {sig_info['signature']}: {e_tx}")
        if not buyers: update.message.reply_text("Nenhuma compra válida."); return
        sorted_buyers = sorted(buyers.items(),key=lambda item:item[1],reverse=True)
        top_10 = sorted_buyers[:10]
        msg = f"🏆 Top {len(top_10)} Compradores ({token_address[:6]}...)\n(Últimas {SIGNATURE_LIMIT} txs)\n\n"
        for i,(wallet,total_sol) in enumerate(top_10): msg+=f"{i+1}. {wallet[:6]}...{wallet[-4:]} - {total_sol:.4f} SOL\n"
        update.message.reply_text(msg)
    except Exception as e_sol_rank: logger.error(f"Erro Solana/ranking: {e_sol_rank}"); update.message.reply_text("Erro ao gerar ranking Solana.")

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
        logger.info("Bot e Dispatcher (v13.x) inicializados e handlers configurados.")
    except Exception as e:
        logger.critical(f"Erro ao inicializar Bot ou Dispatcher (v13.x): {e}", exc_info=True)
        bot_instance = None
        dispatcher = None

# --- Handler Principal da Vercel ---
def handler(event, context_aws_lambda_placeholder):
    if not dispatcher or not bot_instance:
        logger.error("Dispatcher ou Bot não inicializado no handler. Verifique logs de inicialização.")
        return {'statusCode': 500, 'body': json.dumps({'error': 'Bot not configured or initialization failed'})}

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

        # logger.debug(f"Update JSON recebido pelo handler: {json.dumps(update_json, indent=2)}") # Pode ser muito verboso
        update = Update.de_json(update_json, bot_instance)
        dispatcher.process_update(update)
        return {'statusCode': 200, 'body': json.dumps({'message': 'Telegram update processed successfully'})}
    except Exception as e:
        logger.error(f"Erro no handler principal da Vercel: {e}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f'Internal server error: {str(e)}'})
        }
