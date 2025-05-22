# api/bot.py

import os
import sys
import json
import logging
import time

# --- Bloco de Diagnóstico ---
# Imprime o diretório de trabalho atual
print(f"Current working directory: {os.getcwd()}")

print("\n--- Conteúdo da Raiz da Função Vercel (/var/task/) ---")
try:
    # Lista tudo na raiz, incluindo o que a Vercel pode adicionar ou o que vem do seu repo
    print(os.listdir("/var/task/"))
except Exception as e:
    print(f"Erro ao listar /var/task/: {e}")

print("\n--- Conteúdo do Diretório API (/var/task/api/) ---")
try:
    # Se o seu bot.py está em api/bot.py, este diretório existirá.
    if os.path.exists("/var/task/api/"):
        print(os.listdir("/var/task/api/"))
    else:
        print("Diretório /var/task/api/ não existe ou não é acessível a partir daqui.")
except Exception as e:
    print(f"Erro ao listar /var/task/api/: {e}")

print("\n--- Python sys.path (Caminhos de Importação) ---")
# Mostra onde o Python procura por módulos
print(sys.path)
# --- Fim do Bloco de Diagnóstico ---

# Suas importações originais (o erro de 'Dispatcher' acontecerá após os prints acima)
try:
    import telegram
    from telegram.ext import Dispatcher, CommandHandler, CallbackContext, MessageHandler, Filters
    from telegram import Update

    from solana.rpc.api import Client
    from solana.publickey import PublicKey

    import redis # Para Upstash Redis
except ImportError as e:
    print(f"!!! ERRO DE IMPORTAÇÃO DETECTADO APÓS DIAGNÓSTICO: {e} !!!")
    # Se o erro for o de Dispatcher, ele será impresso aqui também.
    # Isso ajuda a confirmar que os prints de diagnóstico rodaram primeiro.
    raise # Re-levanta o erro para que a Vercel o registre como falha na função


# Configurar logging básico para ver saídas nos logs da Vercel
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Carregar Segredos das Variáveis de Ambiente ---
# Lembre-se de configurar estas variáveis no painel da Vercel!
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
SOLANA_RPC_URL = os.environ.get('SOLANA_RPC_URL')
UPSTASH_REDIS_URL = os.environ.get('UPSTASH_REDIS_URL') # Sua URL do Upstash Redis

# --- Inicializar Cliente Redis ---
kv_store = None
if UPSTASH_REDIS_URL:
    try:
        kv_store = redis.from_url(UPSTASH_REDIS_URL)
        kv_store.ping() # Testa a conexão
        logger.info("Conectado com sucesso ao Upstash Redis!")
    except redis.exceptions.ConnectionError as e:
        logger.error(f"Não foi possível conectar ao Upstash Redis: {e}", exc_info=True)
        kv_store = None
    except Exception as e: # Captura outras exceções potenciais do redis.from_url
        logger.error(f"Erro inesperado ao inicializar o cliente Redis: {e}", exc_info=True)
        kv_store = None
else:
    logger.warning("UPSTASH_REDIS_URL não configurada. O bot não poderá persistir o cadastro de tokens.")


# --- Funções dos Comandos ---

def start_command(update: Update, context: CallbackContext):
    logger.info(f"Comando /start recebido do chat_id: {update.message.chat_id}")
    update.message.reply_text("Olá! Sou um bot para ranking de compras de tokens Solana. Use /help para ver os comandos.")

def help_command(update: Update, context: CallbackContext):
    logger.info(f"Comando /help recebido do chat_id: {update.message.chat_id}")
    help_text = """
    Comandos disponíveis:
    /cadastrartoken <endereco_do_token> - Registra um token para monitoramento neste grupo.
    /ranking - Exibe o ranking de compras para o token registrado.
    /meutoken - Verifica qual token está atualmente registrado para este grupo.
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
        PublicKey(token_address) # Validação superficial do endereço
    except ValueError:
        update.message.reply_text(f"Endereço de token inválido: {token_address}")
        logger.warning(f"Tentativa de registrar token inválido: {token_address} para chat_id: {chat_id}")
        return

    if kv_store:
        try:
            redis_key = f"token_config:{chat_id}"
            kv_store.set(redis_key, token_address)
            update.message.reply_text(f"Token {token_address} registrado para este grupo!")
            logger.info(f"Token {token_address} salvo no Redis para chat_id {chat_id} (key: {redis_key})")
        except redis.exceptions.RedisError as e:
            logger.error(f"Erro ao salvar no Redis para chat_id {chat_id}: {e}", exc_info=True)
            update.message.reply_text("Ocorreu um erro ao tentar registrar o token. Tente novamente mais tarde.")
    else:
        update.message.reply_text("AVISO: Serviço de armazenamento (Redis) não está configurado ou falhou ao conectar. O token não pôde ser salvo permanentemente.")
        logger.error(f"Tentativa de registrar token {token_address} para chat_id {chat_id} sem conexão Redis.")

def get_my_token_command(update: Update, context: CallbackContext):
    chat_id = str(update.message.chat_id)
    logger.info(f"Comando /meutoken recebido do chat_id: {chat_id}")
    if kv_store:
        try:
            redis_key = f"token_config:{chat_id}"
            token_address_bytes = kv_store.get(redis_key)
            if token_address_bytes:
                token_address = token_address_bytes.decode('utf-8')
                update.message.reply_text(f"O token atualmente registrado para este grupo é: {token_address}")
                logger.info(f"Token {token_address} recuperado do Redis para chat_id {chat_id} (key: {redis_key})")
            else:
                update.message.reply_text("Nenhum token registrado para este grupo. Use /cadastrartoken.")
                logger.info(f"Nenhum token encontrado no Redis para chat_id {chat_id} (key: {redis_key})")
        except redis.exceptions.RedisError as e:
            logger.error(f"Erro ao ler do Redis para chat_id {chat_id}: {e}", exc_info=True)
            update.message.reply_text("Ocorreu um erro ao tentar verificar o token. Tente novamente mais tarde.")
    else:
        update.message.reply_text("AVISO: Serviço de armazenamento (Redis) não está configurado ou falhou ao conectar. Não é possível verificar o token.")

def ranking_command(update: Update, context: CallbackContext):
    chat_id = str(update.message.chat_id)
    logger.info(f"Comando /ranking recebido do chat_id: {chat_id}")
    token_address = None

    if not kv_store:
        update.message.reply_text("AVISO: Serviço de armazenamento (Redis) não configurado. Não é possível gerar ranking.")
        logger.error(f"Ranking solicitado para chat_id {chat_id} sem conexão Redis.")
        return
    
    try:
        redis_key = f"token_config:{chat_id}"
        token_address_bytes = kv_store.get(redis_key)
        if token_address_bytes:
            token_address = token_address_bytes.decode('utf-8')
            logger.info(f"Token {token_address} recuperado do Redis para ranking no chat_id {chat_id}")
        else:
            update.message.reply_text("Nenhum token registrado para este grupo. Use /cadastrartoken primeiro.")
            logger.info(f"Ranking solicitado para chat_id {chat_id} mas nenhum token encontrado no Redis.")
            return
    except redis.exceptions.RedisError as e:
        logger.error(f"Erro ao buscar token no Redis para ranking (chat_id {chat_id}): {e}", exc_info=True)
        update.message.reply_text("Erro ao buscar configuração do token. Tente novamente.")
        return
    
    update.message.reply_text(f"Processando o ranking para o token {token_address[:10]}... Isso pode levar um momento.")

    try:
        if not SOLANA_RPC_URL:
            update.message.reply_text("URL RPC da Solana não configurada no servidor.")
            logger.error("SOLANA_RPC_URL não está configurada para o ranking.")
            return

        solana_client = Client(SOLANA_RPC_URL)
        token_pk = PublicKey(token_address)
        
        # Limite de assinaturas para buscar (IMPORTANTE para Vercel)
        # Um valor muito alto pode exceder o tempo de execução da Vercel.
        SIGNATURE_LIMIT = 50 # Comece com valores baixos (10-50) e aumente com cuidado!
        logger.info(f"Buscando últimas {SIGNATURE_LIMIT} assinaturas para {token_address}...")

        resp = solana_client.get_signatures_for_address(token_pk, limit=SIGNATURE_LIMIT)
        
        if not resp or 'result' not in resp or not resp['result']:
            update.message.reply_text(f"Nenhuma transação recente encontrada para o token {token_address}.")
            logger.info(f"Nenhuma assinatura encontrada para {token_address} no RPC.")
            return
        
        signatures_info = resp['result']
        logger.info(f"Encontradas {len(signatures_info)} assinaturas para {token_address}.")
        buyers = {}  # {'wallet_address': total_sol_spent}
        processed_count = 0

        for sig_info in signatures_info:
            signature = sig_info['signature']
            # time.sleep(0.05) # Pequeno delay opcional para não sobrecarregar RPCs públicos

            try:
                tx_detail_resp = solana_client.get_transaction(signature, encoding="jsonParsed", commitment="confirmed", max_supported_transaction_version=0)
                tx_detail = tx_detail_resp.get('result')

                if not tx_detail or not tx_detail.get('meta') or tx_detail['meta'].get('err'):
                    logger.debug(f"Transação {signature} ignorada (sem meta, com erro ou sem detalhes).")
                    continue # Pular transações com erro ou sem meta

                meta = tx_detail['meta']
                accounts = tx_detail['transaction']['message']['accountKeys']
                pre_balances_sol = meta['preBalances']
                post_balances_sol = meta['postBalances']
                pre_token_balances = meta.get('preTokenBalances', [])
                post_token_balances = meta.get('postTokenBalances', [])

                # Lógica de identificação de compra (MUITO SIMPLIFICADA - PRECISA MELHORAR)
                if not accounts or not accounts[0]['signer']: continue
                potential_buyer_address = accounts[0]['pubkey'] # Assume que o primeiro signatário é o comprador
                sol_spent_in_tx = 0
                token_received_in_tx = 0

                buyer_sol_idx = next((i for i, acc in enumerate(accounts) if acc['pubkey'] == potential_buyer_address), -1)
                
                if buyer_sol_idx != -1 and len(pre_balances_sol) > buyer_sol_idx and len(post_balances_sol) > buyer_sol_idx:
                    sol_before = pre_balances_sol[buyer_sol_idx]
                    sol_after = post_balances_sol[buyer_sol_idx]
                    if sol_before > sol_after: # SOL diminuiu
                        sol_spent_in_tx = (sol_before - sol_after) / 10**9 # Lamports to SOL

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
                        if amount_post > amount_pre: # Token aumentou
                            token_received_in_tx = amount_post - amount_pre
                            break 
                
                # Condição de compra: SOL gasto > 0, Token recebido > 0
                # E idealmente, verificar se foi uma interação com uma DEX (ex: logMessages)
                # Esta lógica de 'is_dex_tx' é um placeholder e precisa ser implementada corretamente!
                is_dex_tx = True # REMOVER/SUBSTITUIR: Implementar verificação de logs de DEX!

                if sol_spent_in_tx > 0.00001 and token_received_in_tx > 0 and is_dex_tx: # Umbral mínimo para SOL
                    buyers[potential_buyer_address] = buyers.get(potential_buyer_address, 0) + sol_spent_in_tx
                    logger.debug(f"Compra (potencial) detectada: {potential_buyer_address} comprou {token_received_in_tx} do token gastando {sol_spent_in_tx} SOL na tx {signature}")
                
                processed_count += 1
            except Exception as e:
                logger.error(f"Erro ao processar tx {signature} no ranking: {e}", exc_info=True)
                continue 
        
        logger.info(f"Total de transações analisadas no ranking: {processed_count} de {len(signatures_info)} assinaturas.")
        if not buyers:
            update.message.reply_text("Nenhuma compra válida identificada nas transações recentes analisadas para este token.")
            logger.info(f"Nenhum comprador encontrado para token {token_address} após análise.")
            return

        sorted_buyers = sorted(buyers.items(), key=lambda item: item[1], reverse=True)
        top_10 = sorted_buyers[:10]

        message = f"🏆 Top {len(top_10)} Compradores do Token ({token_address[:6]}...) 🏆\n(Analisadas as últimas {SIGNATURE_LIMIT} transações envolvendo o token)\n\n"
        for i, (wallet, total_sol) in enumerate(top_10):
            short_wallet = f"{wallet[:6]}...{wallet[-4:]}"
            message += f"{i+1}. {short_wallet} - {total_sol:.4f} SOL\n"
        update.message.reply_text(message)
        logger.info(f"Ranking enviado para token {token_address} no chat_id {chat_id}")

    except Exception as e:
        logger.error(f"Erro crítico no comando /ranking para token {token_address} no chat_id {chat_id}: {e}", exc_info=True)
        update.message.reply_text(f"Ocorreu um erro ao gerar o ranking. Tente novamente mais tarde.")


# --- Configuração do Bot e Dispatcher ---
# É crucial que TELEGRAM_BOT_TOKEN seja carregado corretamente.
if not TELEGRAM_BOT_TOKEN:
    logger.critical("TELEGRAM_BOT_TOKEN não encontrado nas variáveis de ambiente! O bot não pode iniciar.")
    # Em um cenário serverless, não há um "loop de polling" para parar,
    # mas a função handler não funcionará corretamente sem o token.
    bot_instance = None
    dispatcher = None
else:
    try:
        bot_instance = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
        # workers=0 é recomendado para ambientes serverless como Vercel
        # para evitar criação de threads desnecessárias.
        dispatcher = Dispatcher(bot_instance, None, workers=0, use_context=True)

        # Adicionar Handlers de Comando
        dispatcher.add_handler(CommandHandler("start", start_command))
        dispatcher.add_handler(CommandHandler("help", help_command))
        dispatcher.add_handler(CommandHandler("cadastrartoken", register_token_command))
        dispatcher.add_handler(CommandHandler("meutoken", get_my_token_command))
        dispatcher.add_handler(CommandHandler("ranking", ranking_command))
        # Você pode adicionar mais handlers aqui (ex: MessageHandler para comandos desconhecidos)
    except Exception as e:
        logger.critical(f"Erro ao inicializar o Bot ou Dispatcher: {e}", exc_info=True)
        bot_instance = None
        dispatcher = None


# --- Handler Principal da Vercel ---
# A Vercel espera uma função chamada 'handler' no arquivo especificado (ex: api/bot.py)
def handler(event, context_aws_lambda_placeholder): # O segundo argumento é convenção do Lambda, Vercel pode não usá-lo ativamente
    if not dispatcher or not bot_instance:
        logger.error("Dispatcher ou Bot não inicializado. Verifique o token do Telegram e outros erros de inicialização.")
        return {'statusCode': 500, 'body': json.dumps({'error': 'Bot not configured or failed to initialize'})}
    
    try:
        # A Vercel geralmente passa o corpo da requisição HTTP já como um dict (se JSON)
        # ou como uma string JSON que precisa ser parseada.
        if isinstance(event, str): # Se Vercel passar como string JSON
            logger.debug("Evento recebido como string, parseando JSON.")
            update_json = json.loads(event)
        elif isinstance(event, dict) and 'body' in event: # Comum se Vercel emula API Gateway
            logger.debug("Evento recebido como dict com 'body', parseando 'body'.")
            # O corpo pode ser uma string JSON ou já um dict, dependendo da configuração da Vercel/Gateway
            if isinstance(event['body'], str):
                update_json = json.loads(event['body'])
            else:
                update_json = event['body'] # Assume que event['body'] já é um dict
        else: # Assume que 'event' já é o update JSON como dict
            logger.debug("Evento recebido diretamente como dict.")
            update_json = event

        logger.info(f"Update JSON recebido: {json.dumps(update_json, indent=2)}") # Cuidado ao logar dados sensíveis

        update = Update.de_json(update_json, bot_instance)
        dispatcher.process_update(update)

        return {
            'statusCode': 200,
            'body': json.dumps({'message': 'Telegram update processed successfully'})
        }
    except json.JSONDecodeError as e:
        logger.error(f"Erro ao decodificar JSON do evento: {e}. Corpo do evento (parcial): {str(event)[:500]}", exc_info=True)
        return {'statusCode': 400, 'body': json.dumps({'error': 'Bad JSON format in request body'})}
    except Exception as e:
        logger.error(f"Erro inesperado no handler principal da Vercel: {e}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f'Internal server error: {str(e)}'})
        }

# Opcional: Função para configurar o webhook (para rodar localmente uma vez ou via script)
# Lembre-se de usar seu NOVO e SEGURO token aqui.
# E a URL correta do seu deploy na Vercel.
# def set_webhook_once():
#     if not bot_instance:
#         print("Instância do Bot não criada. Verifique o token.")
#         return
#     VERCEL_PROJECT_URL = os.environ.get("VERCEL_URL") # Vercel injeta esta variável em builds
#     if VERCEL_PROJECT_URL:
#         # O path /api/bot deve corresponder à localização do seu arquivo handler
#         webhook_url = f"https://{VERCEL_PROJECT_URL}/api/bot"
#         if bot_instance.set_webhook(webhook_url):
#             print(f"Webhook configurado para: {webhook_url}")
#         else:
#             print(f"Falha ao configurar o webhook para: {webhook_url}")
#     else:
#         print("Variável VERCEL_URL não encontrada nas variáveis de ambiente.")
#         print("Configure o webhook manualmente usando curl ou acesse a URL do Telegram API no navegador.")
#         print("Exemplo de URL para navegador (substitua placeholders):")
#         print(f"https://api.telegram.org/botSEU_TOKEN_AQUI/setWebhook?url=https://SEU_PROJETO.vercel.app/api/bot")

# if __name__ == "__main__":
#     # Este bloco é útil para testes locais com polling, mas não será executado na Vercel.
#     # Certifique-se de que as variáveis de ambiente estão disponíveis localmente se for testar assim.
#     # Por exemplo, usando um arquivo .env e a biblioteca python-dotenv.
#     if TELEGRAM_BOT_TOKEN and SOLANA_RPC_URL and UPSTASH_REDIS_URL:
#         print("Iniciando bot com polling para teste local...")
#         # Para teste local, é mais fácil usar o Updater com polling.
#         # O Dispatcher já está configurado acima, mas o Updater gerencia o loop de polling.
#         # Nota: O Dispatcher usado no handler da Vercel é um pouco diferente em como é alimentado.
#         from telegram.ext import Updater
#         updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)
#         dp = updater.dispatcher # Pega o dispatcher do updater

#         # Adicionar Handlers de Comando (se não foram adicionados ao dispatcher global)
#         # Se o dispatcher global já foi populado, esta parte pode não ser necessária ou pode ser ajustada.
#         dp.add_handler(CommandHandler("start", start_command))
#         dp.add_handler(CommandHandler("help", help_command))
#         dp.add_handler(CommandHandler("cadastrartoken", register_token_command))
#         dp.add_handler(CommandHandler("meutoken", get_my_token_command))
#         dp.add_handler(CommandHandler("ranking", ranking_command))
        
#         updater.start_polling()
#         logger.info("Bot iniciado localmente com polling. Pressione Ctrl+C para parar.")
#         updater.idle()
#     else:
#         print("Variáveis de ambiente não configuradas para teste local. Configure TELEGRAM_BOT_TOKEN, SOLANA_RPC_URL, UPSTASH_REDIS_URL.")
    
    # Para configurar o webhook uma vez:
    # print("Tentando configurar o webhook (se VERCEL_URL estiver disponível)...")
    # set_webhook_once()
