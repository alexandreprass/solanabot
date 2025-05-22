# api/bot.py (Tentativa de limpar sys.modules e usar PTB v13.15)

import sys
import os
import json
import logging
import time

# --- Workaround Avançado: Tentativa de limpar sys.modules ---
print(f"--- INÍCIO DO SCRIPT: Tentando resolver conflito de 'telegram' com sys.modules ---")
print(f"sys.path INICIAL: {sys.path}")

CONFLICTING_MODULE_PATH_PREFIX = "/var/task/telegram"
MODULE_NAME_TO_CHECK = "telegram"

if MODULE_NAME_TO_CHECK in sys.modules:
    cached_module = sys.modules[MODULE_NAME_TO_CHECK]
    cached_module_file = getattr(cached_module, '__file__', None)
    print(f"Módulo '{MODULE_NAME_TO_CHECK}' encontrado no cache sys.modules.")
    print(f"Localização do módulo cacheado (cached_module.__file__): {cached_module_file}")

    if cached_module_file and cached_module_file.startswith(CONFLICTING_MODULE_PATH_PREFIX):
        print(f"O módulo '{MODULE_NAME_TO_CHECK}' cacheado vem de '{CONFLICTING_MODULE_PATH_PREFIX}'. Tentando remover do cache...")
        try:
            del sys.modules[MODULE_NAME_TO_CHECK]
            # Verifica se realmente foi removido
            if MODULE_NAME_TO_CHECK not in sys.modules:
                print(f"SUCESSO: Módulo '{MODULE_NAME_TO_CHECK}' removido de sys.modules.")
            else:
                print(f"!!! FALHA ao remover '{MODULE_NAME_TO_CHECK}' de sys.modules. Ainda está no cache. !!!")
        except Exception as e_del_cache:
            print(f"!!! ERRO ao tentar deletar '{MODULE_NAME_TO_CHECK}' de sys.modules: {e_del_cache} !!!")
    else:
        print(f"Módulo '{MODULE_NAME_TO_CHECK}' cacheado não parece ser o conflitante de '{CONFLICTING_MODULE_PATH_PREFIX}'. Nenhuma ação de remoção do cache tomada para ele.")
else:
    print(f"Módulo '{MODULE_NAME_TO_CHECK}' não encontrado inicialmente no cache sys.modules.")

# Re-tentativa de priorizar site-packages no sys.path (pode ser redundante se sys.modules foi limpo, mas não custa)
SITE_PACKAGES_PATH = '/var/lang/lib/python3.12/site-packages' # Ajuste se a versão do Python mudar nos logs
if SITE_PACKAGES_PATH not in sys.path:
    sys.path.insert(0, SITE_PACKAGES_PATH)
elif sys.path.index(SITE_PACKAGES_PATH) > 0: # Se existe mas não é o primeiro
    sys.path.pop(sys.path.index(SITE_PACKAGES_PATH))
    sys.path.insert(0, SITE_PACKAGES_PATH)
print(f"sys.path APÓS manipulações: {sys.path}")
# --- Fim do Workaround Avançado ---


try:
    print("\n--- Tentando importar bibliotecas principais APÓS TODOS OS WORKAROUNDS ---")
    import telegram # Esta é a importação crítica
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

# (O restante do seu código do bot v13.15 permanece aqui)
# ... cole aqui as definições de logger, variáveis de ambiente, kv_store, ...
# ... start_command, help_command, register_token_command, get_my_token_command, ranking_command ...
# ... configuração do bot_instance, dispatcher, e a função handler da Vercel ...
# (Use o restante do código da minha penúltima resposta, onde forneci o bot completo para v13.15)

# Configurar logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
SOLANA_RPC_URL = os.environ.get('SOLANA_RPC_URL')
UPSTASH_REDIS_URL = os.environ.get('UPSTASH_REDIS_URL')

kv_store = None
if UPSTASH_REDIS_URL:
    try:
        kv_store = redis.from_url(UPSTASH_REDIS_URL)
        kv_store.ping(); logger.info("Conectado ao Redis!")
    except Exception as e: logger.error(f"Erro Redis: {e}")
else: logger.warning("URL Redis não configurada.")

def start_command(update: Update, context: CallbackContext):
    update.message.reply_text("Olá! Bot de Ranking Solana. /help para comandos.")
def help_command(update: Update, context: CallbackContext):
    update.message.reply_text("Comandos: /cadastrartoken <addr>, /ranking, /meutoken")
def register_token_command(update: Update, context: CallbackContext):
    chat_id = str(update.message.chat_id)
    if not context.args: update.message.reply_text("Uso: /cadastrartoken <addr>"); return
    token_addr = context.args[0]
    try: PublicKey(token_addr)
    except Exception: update.message.reply_text(f"Endereço inválido: {token_addr}"); return
    if kv_store:
        try: kv_store.set(f"token_config:{chat_id}", token_addr); update.message.reply_text(f"Token {token_addr} registrado!")
        except Exception as e: logger.error(f"Erro Redis: {e}"); update.message.reply_text("Erro ao registrar.")
    else: update.message.reply_text("AVISO: Redis não configurado.")
def get_my_token_command(update: Update, context: CallbackContext):
    chat_id = str(update.message.chat_id)
    if kv_store:
        try:
            val = kv_store.get(f"token_config:{chat_id}")
            if val: update.message.reply_text(f"Token: {val.decode('utf-8')}")
            else: update.message.reply_text("Nenhum token registrado.")
        except Exception as e: logger.error(f"Erro Redis: {e}"); update.message.reply_text("Erro ao verificar.")
    else: update.message.reply_text("AVISO: Redis não configurado.")
def ranking_command(update: Update, context: CallbackContext):
    chat_id = str(update.message.chat_id)
    if not kv_store: update.message.reply_text("AVISO: Redis não configurado."); return
    try:
        val = kv_store.get(f"token_config:{chat_id}")
        if not val: update.message.reply_text("Nenhum token registrado."); return
        token_address = val.decode('utf-8')
    except Exception as e: logger.error(f"Erro Redis: {e}"); update.message.reply_text("Erro config."); return
    update.message.reply_text(f"Processando ranking para {token_address[:10]}...")
    try:
        if not SOLANA_RPC_URL: update.message.reply_text("URL RPC Solana não configurada."); return
        solana_client = Client(SOLANA_RPC_URL); token_pk = PublicKey(token_address)
        SIGNATURE_LIMIT = 50
        resp = solana_client.get_signatures_for_address(token_pk, limit=SIGNATURE_LIMIT)
        if not resp or 'result' not in resp or not resp['result']: update.message.reply_text(f"Nenhuma tx recente."); return
        sig_infos = resp['result']; buyers = {}
        for sig_info in sig_infos:
            try:
                tx_detail_resp = solana_client.get_transaction(sig_info['signature'], encoding="jsonParsed", commitment="confirmed", max_supported_transaction_version=0)
                tx_detail = tx_detail_resp.get('result')
                if not tx_detail or not tx_detail.get('meta') or tx_detail['meta'].get('err'): continue
                meta, accs = tx_detail['meta'], tx_detail['transaction']['message']['accountKeys']
                if not accs or not accs[0]['signer']: continue
                buyer, sol_spent, tk_recv = accs[0]['pubkey'], 0, 0
                idx = next((i for i,a in enumerate(accs) if a['pubkey']==buyer),-1)
                if idx!=-1 and len(meta['preBalances'])>idx and len(meta['postBalances'])>idx and meta['preBalances'][idx]>meta['postBalances'][idx]:
                    sol_spent=(meta['preBalances'][idx]-meta['postBalances'][idx])/10**9
                for tb_post in meta.get('postTokenBalances',[]):
                    if tb_post.get('owner')==buyer and tb_post.get('mint')==token_address:
                        post_amt=float(tb_post.get('uiTokenAmount',{}).get('uiAmountString','0') or '0')
                        pre_amt=0.0
                        for tb_pre in meta.get('preTokenBalances',[]):
                            if tb_pre.get('owner')==buyer and tb_pre.get('mint')==token_address:
                                pre_amt=float(tb_pre.get('uiTokenAmount',{}).get('uiAmountString','0') or '0'); break
                        if post_amt>pre_amt: tk_recv=post_amt-pre_amt; break
                if sol_spent>1e-5 and tk_recv>0: buyers[buyer]=buyers.get(buyer,0)+sol_spent
            except Exception as e_tx: logger.error(f"Erro tx {sig_info['signature']}: {e_tx}")
        if not buyers: update.message.reply_text("Nenhuma compra válida."); return
        sorted_buyers = sorted(buyers.items(),key=lambda item:item[1],reverse=True)
        top_10 = sorted_buyers[:10]
        msg=f"🏆 Top {len(top_10)} Compradores ({token_address[:6]}...)\n(Últimas {SIGNATURE_LIMIT} txs)\n\n"
        for i,(w,s) in enumerate(top_10): msg+=f"{i+1}. {w[:6]}...{w[-4:]} - {s:.4f} SOL\n"
        update.message.reply_text(msg)
    except Exception as e_sol: logger.error(f"Erro Solana/ranking: {e_sol}"); update.message.reply_text("Erro ranking Solana.")

bot_instance, dispatcher = None, None
if TELEGRAM_BOT_TOKEN:
    try:
        bot_instance = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
        dispatcher = Dispatcher(bot_instance, None, workers=0, use_context=True)
        cmds = [("start",start_command),("help",help_command),("cadastrartoken",register_token_command),("meutoken",get_my_token_command),("ranking",ranking_command)]
        for cmd_name, cmd_func in cmds: dispatcher.add_handler(CommandHandler(cmd_name, cmd_func))
        logger.info("Bot e Dispatcher (v13.x) inicializados.")
    except Exception as e: logger.critical(f"Erro init Bot/Dispatcher: {e}"); bot_instance=None; dispatcher=None

def handler(event, context):
    if not dispatcher or not bot_instance: return {'statusCode':500,'body':json.dumps({'error':'Bot not init'})}
    try:
        if isinstance(event,str):update_json=json.loads(event)
        elif isinstance(event,dict) and 'body' in event: update_json=json.loads(event['body']) if isinstance(event['body'],str) else event['body']
        else: update_json=event
        update=Update.de_json(update_json,bot_instance)
        dispatcher.process_update(update)
        return {'statusCode':200,'body':json.dumps({'message':'Update processed'})}
    except Exception as e: logger.error(f"Erro handler: {e}"); return {'statusCode':500,'body':json.dumps({'error':f'Internal error: {str(e)}'})}
